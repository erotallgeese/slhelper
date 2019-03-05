#!/usr/bin/env python3

import SoftLayer
import json
import string
import os
import requests
import re
import datetime
from dateutil.parser import parse as dateparser
from dateutil.relativedelta import relativedelta
import sys
import pathlib

# helper class to get info from IBM Softlayer
class slhelper:
    def __init__(self, username, api_key, debug=False):
        self.username = username
        self.api_key = api_key
        self.debug = debug

        self.client = SoftLayer.Client(username=self.username, api_key=self.api_key)

        self.item_list = []
        self.preset_list = []
        self.location_list = []
        self.storage = {}

        slPath = os.path.dirname(os.path.abspath(__file__))
        self.f_items = '{}/{}'.format(slPath, "ibm.items")
        self.f_presets = '{}/{}'.format(slPath, "ibm.presets")
        self.f_datecenters = '{}/{}'.format(slPath, "ibm.datecenters")
        self.f_storages = '{}/{}'.format(slPath, "ibm.storages")
        
    def __LoadItems(self):
        if not self.item_list:
            mask='mask[itemCategory, prices[capacityRestrictionMaximum]]'
            if self.debug:
                if not os.path.isfile(self.f_items):
                    items = self.client["SoftLayer_Product_Package"].getItems(id=835, mask=mask)
                    json.dump(items, open(self.f_items,'w'), indent=4)
                self.item_list = json.load(open(self.f_items))
            else:
                self.item_list = self.client["SoftLayer_Product_Package"].getItems(id=835, mask=mask)

    def __loadPreset(self):
        if not self.preset_list:
            objectFilter = { "package": { "keyName": { "operation": "PUBLIC_CLOUD_SERVER" } } }
            mask = "mask[locations,computeGroup,package,configuration[category,price]]"
            if self.debug:
                if not os.path.isfile(self.f_presets):
                    presets = self.client['Product_Package_Preset'].getAllObjects(mask=mask, filter=objectFilter)
                    json.dump(presets, open(self.f_presets,'w'), indent=4)
                self.preset_list = json.load(open(self.f_presets))
            else:
                self.preset_list = self.client['Product_Package_Preset'].getAllObjects(mask=mask, filter=objectFilter)

    def __loadStorage(self):
        if not self.storage:
            objectMask= 'mask[prices]'
            # filter for iops 2 only
            objectFilter = { "items": { "keyName": { "operation": "STORAGE_SPACE_FOR_2_IOPS_PER_GB" } } }
            if self.debug:
                if not os.path.isfile(self.f_storages):
                    storages = self.client['SoftLayer_Product_Package'].getItems(id=759, filter=objectFilter, mask=objectMask)[0]
                    json.dump(storages, open(self.f_storages,'w'), indent=4)
                self.storage = json.load(open(self.f_storages))
            else:
                self.storage = self.client['SoftLayer_Product_Package'].getItems(id=759, filter=objectFilter, mask=objectMask)[0]

    def __loadDatacenter(self):
        if not self.location_list:
            self.__parseDatacenterLocation()
        
    def __findItemPrice(self, categoryCode, priceId):
        for item in self.item_list:
            if item['itemCategory']['categoryCode'] == categoryCode:
                for ii in item['prices']:
                    if ii['id'] == priceId:
                        return item

    def __findOS(self, softwareDescriptionId):
        for item in self.item_list:
            if item['softwareDescriptionId'] == softwareDescriptionId and item['itemCategory']['categoryCode'] == 'os':
                return item
                
    def __parseDatacenterLocation(self):
        mask = 'priceGroups, regions, groups'
        if self.debug:
            if not os.path.isfile(self.f_datecenters):
                datecenters = self.client["SoftLayer_Location_Datacenter"].getDatacenters(mask=mask)
                json.dump(datecenters, open(self.f_datecenters,'w'), indent=4)
            else:
                datecenters = json.load(open(self.f_datecenters))
        else:
            datecenters = self.client["SoftLayer_Location_Datacenter"].getDatacenters(mask=mask)

        # reverse the order for keep newer dc (i.e. dal13 is newer that dal01, keep dal13)
        datecenters.sort(key=lambda x: x['name'], reverse=True)

        dc_list = []
        self.location_list = []
        for location in datecenters:
            # check group
            hasLocation = False
            for group in location['groups']:
                if (group['locationGroupType']['name'] == "PRICING" or
                    group['locationGroupType']['name'] == "REGIONAL"):
                    hasLocation = True
                    break
            if not hasLocation:
                continue

            # only keep one dc for one location
            dc = location['name'][:3]
            if dc in dc_list:
                continue
            else:
                dc_list.append(dc)

            tmp_dict = {
                'provider': 'IBM',
                'dc': location['name'],
                'country':location['regions'][0]['description'].split("-")[1].strip(),
                'priceGroupId': ''
            }
            
            # find its priceGroupId
            for priceGroup in location['priceGroups']:
                if priceGroup['name'].startswith("Location Group"):
                    tmp_dict['priceGroupId'] = priceGroup['id']
                    break
            
            self.location_list.append(tmp_dict)
        self.location_list.sort(key=lambda x: x['dc'])
        return self.location_list
        
    def __getPrice(self, price_list, priceId, locationId):
        plen = len(price_list)
        #print('test', plen, priceId, 'a', locationId, 'b')
        if plen > 0:
            # perfect case
            for item in price_list:
                if item['id'] == priceId and item['locationGroupId'] == locationId:
                    return round(float(item['hourlyRecurringFee']) * 24 * 30, 2)
            # there still 2 cases:
            #    1. the list contain priceId but the real price is located at another object in this list
            #    2. the list get only one object with empty locationGroupId
            for item in price_list:
                if item['id'] == priceId:
                    # find again...
                    for l2 in price_list:
                        if l2['locationGroupId'] == locationId:
                            return round(float(l2['hourlyRecurringFee']) * 24 * 30, 2)

                    # some item's locationGroupId would be empty
                    #print('test2', plen, priceId, 'a', locationId, 'b')
                    return round(float(item['hourlyRecurringFee']) * 24 * 30, 2)

    # for serviceInfo.json
    def getDatacenterMap(self):
        print('{')
        for item in self.location_list:
            print('\"{}\": \"{}\",'.format(item['country'], item['dc'])) 
        print('}')
        
    # for region_country_code.json
    def getRegionMap(self):
        for item in self.location_list:
            print('{')
            print('    \"provider\": \"IBM\",')
            print('    \"region\": \"{}\",'.format(item['dc']))
            print('    \"country\": \"{}\"'.format(item['country']))
            print('},')
            
    def getPresets(self):
        self.__LoadItems()
        self.__loadPreset()
        self.__loadStorage()
        self.__loadDatacenter()
        
        preset_list = []
        for preset in self.preset_list:
            if ('package' in preset and
                preset['package']['keyName'] == "PUBLIC_CLOUD_SERVER"):

                # vm info
                tmp_dict = dict()
                tmp_dict['provider'] = 'IBM'
                tmp_dict['productType'] = preset['computeGroup']['keyName']
                tmp_dict['instanceType'] = preset['keyName'].replace('_', '.')
                #tmp_dict['name'] = preset['name']
                ins = preset['keyName'].split('_')[1].split('X')
                tmp_dict['vcpu'] = ins[0]
                tmp_dict['memory'] = ins[1]
                tmp_dict['disk'] = ins[2]

                # parse for configuration
                conf_dict = dict()
                for conf in preset['configuration']:
                    if conf['category']['categoryCode'] == 'guest_core':
                        conf_dict['guest_core'] = conf['price']['id']
                    elif conf['category']['categoryCode'] == 'ram':
                        conf_dict['ram'] = conf['price']['id']
                    elif conf['category']['categoryCode'] == 'guest_disk0':
                        conf_dict['guest_disk0'] = conf['price']['id']
                    elif conf['category']['categoryCode'] == 'guest_pcie_device0':
                        conf_dict['guest_pcie_device0'] = conf['price']['id']
                assert(len(conf_dict) >= 3)
                if self.debug:
                    tmp_dict['conf'] = conf_dict

                # collect for price component
                price_dict = dict()
                for key in conf_dict:
                    price_dict[key] = self.__findItemPrice(key, conf_dict[key])
                    assert(bool(price_dict[key]) == True)
                if self.debug:
                    tmp_dict['price_ref'] = price_dict

                # create an map point form its key to groupid
                dc_map = dict()
                for dc in self.location_list:
                    dc_map[dc['dc']] = dc['priceGroupId']

                # accumulate the price
                hasPrice = False
                price2_dict = dict()
                for dc in self.location_list:
                    dc_key = dc['dc']
                    dc_key_discribe = '{}_d'.format(dc_key)

                    # check location support
                    hasSupport = False
                    if len(preset['locations']) == 0:
                        hasSupport = True
                    else:
                        for p in preset['locations']:
                            if p['name'] == dc_key:
                                hasSupport = True
                                break
                    if hasSupport:
                        acc_value = 0
                        if self.debug:
                            price2_dict[dc_key_discribe] = ''
                        for key in conf_dict:
                            a_value = self.__getPrice(price_dict[key]['prices'], conf_dict[key], dc_map[dc_key])
                            if self.debug:
                                price2_dict[dc_key_discribe] += '{}: {}, '.format(key, a_value)
                            acc_value += float(a_value)
                        #price2_dict[dc_key] = format(round(acc_value, 2), '.2f') # padding zeros
                        price2_dict[dc_key] = round(acc_value, 2)
                        hasPrice = True
                    else:
                        if self.debug:
                            price2_dict[dc_key_discribe] = None
                        price2_dict[dc_key] = None
                tmp_dict['price'] = price2_dict

                if hasPrice:
                    preset_list.append(tmp_dict)

        return sorted(preset_list, key=lambda k: k['instanceType'])
        
    def getDataTransferPrice(self):
        self.__loadDatacenter()

        # price map
        p_map = {
            'dal': 0.09,
            'mon': 0.09,
            'tor': 0.09,
            'mex': 0.18,
            'ams': 0.09,
            'lon': 0.09,
            'fra': 0.09,
            'par': 0.12,
            'mil': 0.12,
            'osl': 0.14,
            'seo': 0.12,
            'sng': 0.12,
            'hkg': 0.14,
            'tok': 0.14,
            'mel': 0.14,
            'syd': 0.14,
            'sao': 0.18,
            'che': 0.18
        }
        p_list = []
        for dc in self.location_list:
            dc_key = dc['dc'][:3]
            price = p_map['dal']    # default price
            if dc_key in p_map:
                price = p_map[dc_key]
            
            tmp_dict = {
                'provider': 'IBM',
                'productType': 'DATA_TRANSFER',
                #'startRange': 250,
                'startRange': 0,
                'dc': dc['dc'],
                'price': price
            }
            p_list.append(tmp_dict)

        return p_list


    def getOS(self):
        url ='https://{}:{}@api.softlayer.com/rest/v3/SoftLayer_Virtual_Guest_Block_Device_Template_Group/getVhdImportSoftwareDescriptions.json'.format(self.username, self.api_key)
        
        retry = 3
        while retry > 0:
            retry -= 1
            response = requests.get(url)
            if response.status_code == 200:
                break
                
        os_list = []
        assert(response.status_code == 200)
        if response.status_code == 200:
            for item in response.json():
                # filter for LAMP type of os
                if 'lamp' in item['longDescription'].lower():
                    continue

                # filter for 32 bits of os
                m = re.search(r'_32$', item['referenceCode'])
                if m is not None:
                    continue

                # filter for ubuntu 12
                m = re.search(r'^UBUNTU_12', item['referenceCode'])
                if m is not None:
                    continue

                # filter for other
                m = re.search(r'^OTHER', item['referenceCode'])
                if m is not None:
                    continue

                # filter for win 2003
                m = re.search(r'^WIN_2003', item['referenceCode'])
                if m is not None:
                    continue

                # filter for win 2008
                m = re.search(r'^WIN_2008', item['referenceCode'])
                if m is not None:
                    continue

                category = item['manufacturer']
                if category == 'Microsoft':
                    category = 'Windows'
                    
                tmp_dict = {
                    'provider': 'IBM',
                    'productType': 'OS_IMAGE',
                    'description': item['longDescription'],
                    'category': category,
                    'referenceCode': item['referenceCode']
                }
                os_list.append(tmp_dict)

        #os_list = sorted(os_list, key=lambda k: k['referenceCode'], reverse=True) 

        assert(len(os_list) > 0)
        return os_list
        
        
    def getOSPrice(self):
        self.__LoadItems()

        url ='https://{}:{}@api.softlayer.com/rest/v3/SoftLayer_Virtual_Guest_Block_Device_Template_Group/getVhdImportSoftwareDescriptions.json'.format(self.username, self.api_key)
        
        retry = 3
        while retry > 0:
            retry -= 1
            response = requests.get(url)
            if response.status_code == 200:
                break
                
        os_list = []
        assert(response.status_code == 200)
        if response.status_code == 200:
            for item in response.json():
                # filter for LAMP type of os
                if 'lamp' in item['longDescription'].lower():
                    continue

                # filter for 32 bits of os
                m = re.search(r'_32$', item['referenceCode'])
                if m is not None:
                    continue

                # filter for ubuntu 12
                m = re.search(r'^UBUNTU_12', item['referenceCode'])
                if m is not None:
                    continue

                # filter for other
                m = re.search(r'^OTHER', item['referenceCode'])
                if m is not None:
                    continue

                # filter for win 2003
                m = re.search(r'^WIN_2003', item['referenceCode'])
                if m is not None:
                    continue

                # filter for win 2008
                m = re.search(r'^WIN_2008', item['referenceCode'])
                if m is not None:
                    continue

                os_item = self.__findOS(item['id'])
                if os_item:
                    category = item['manufacturer']
                    if category == 'Microsoft':
                        category = 'Windows'

                    # collect price info
                    tier = dict()
                    assert(len(os_item['prices']) >= 1)
                    if len(os_item['prices']) == 1:
                        #tier['0'] = float(os_item['prices'][0]['recurringFee'])
                        tier['0'] = round(float(os_item['prices'][0]['hourlyRecurringFee']) * 24 * 30, 2)
                    else:
                        for price_item in os_item['prices']:
                            #tier[price_item['capacityRestrictionMaximum']] = float(price_item['recurringFee'])
                            tier[price_item['capacityRestrictionMaximum']] = round(float(price_item['hourlyRecurringFee']) * 24 * 30, 2)

                    tmp_dict = {
                        'provider': 'IBM',
                        'productType': 'OS_IMAGE',
                        'description': item['longDescription'],
                        'category': category,
                        'referenceCode': item['referenceCode'],
                        'tier': tier
                    }
                    os_list.append(tmp_dict)

        os_list = sorted(os_list, key=lambda k: k['referenceCode'], reverse=True) 

        assert(len(os_list) > 0)
        return os_list

    def getStoragePrice(self):
        self.__loadStorage()
        self.__loadDatacenter()

        assert(len(self.storage) > 0)
        storage_list = list()
        
        for dc in self.location_list:
            price = 0
            for p in self.storage['prices']:
                if dc['priceGroupId'] == p['locationGroupId']:
                    price = float(p['usageRate'])
                    break
            assert(price > 0)
        
            tmp_dict = {
                'provider': 'IBM',
                'productType': 'STORAGE_SPACE',
                'capacityMinimum': self.storage['capacityMinimum'],
                'capacityMaximum': self.storage['capacityMaximum'],
                'dc': dc['dc'],
                'price': price
            }
            storage_list.append(tmp_dict)
        return storage_list

    def getSshKeyList(self):
        sshManager = SoftLayer.managers.sshkey.SshKeyManager(self.client)

        key_list = []
        kl = sshManager.list_keys()
        for k in kl:
            key_list.append({'name':k['label'], 'id':str(k['id'])})
        return key_list

    def createSshKey(self, keyName):
        from Crypto.PublicKey import RSA

        key = RSA.generate(4096)
        pubkey = key.publickey()

        # setup public key to softlayer
        try:
            sshManager = SoftLayer.managers.sshkey.SshKeyManager(self.client)
            result = sshManager.add_key(pubkey.exportKey('OpenSSH').decode(), keyName)
        except:
            return {'error': 'Unable to Add key'}

        return {'id': result['id'], 'privatekey': key.exportKey('PEM').decode()}

    def getBrandAllOwnedAccounts(self, needInvoice=True):
        # test
        return self.__getThisAccounts()

        # get all brands, suppose there is one brand for now.
        ownedBrands = self.client["SoftLayer_Account"].getOwnedBrands()
        assert(len(ownedBrands) == 1)
        for brand in ownedBrands:
            # retrieve all accounts under this brand
            # i have no idea why, but this filter could be used to reduce recursive inner allOwnedAccounts
            brandFilter = { 'allOwnedAccounts': {} }
            # it seems like that it's not be able to get SoftLayer_Account from brand apikey, so we need add the mask for invoice info.
            # also, it seems not be able to filter for 'typeCode' for invoices.
            brandMask = None
            if needInvoice == True:
                brandMask = 'mask[invoices]'
            allOwnedAccounts = self.client["SoftLayer_Brand"].getAllOwnedAccounts(id=brand['id'], filter=brandFilter, mask=brandMask)
        return allOwnedAccounts

    # this api is used for test to let its behavior is simular to getBrandAllOwnedAccounts
    def __getThisAccounts(self):
        accountList = []
        accountMask = "mask[invoices]"
        accountList.append(self.client["SoftLayer_Account"].getObject(mask=accountMask))
        return accountList

    def downloadInvoicePdf(self, invoiceId, path=''):
        ret = { 'err': '', 'fileName': '' }
        try:
            pdfFilename = self.client["SoftLayer_Billing_Invoice"].getPdfFilename(id=invoiceId)
            fName = os.path.join(path, pdfFilename)
            pdf = self.client["SoftLayer_Billing_Invoice"].getPdf(id=invoiceId)
            with open(fName, "wb") as pdfFile:
                pdfFile.write(pdf.data)
            ret['fileName'] = pdfFilename
        except:
            ret['err'] = sys.exc_info()[0]
            #print("downloadInvoicePdf Unexpected error:", ret['err'])
        return ret

    def downloadInvoicePdfDetailed(self, invoiceId, path=''):
        ret = { 'err': '', 'fileName': '' }
        try:
            pdfDetailedFilename = self.client["SoftLayer_Billing_Invoice"].getPdfDetailedFilename(id=invoiceId)
            fName = os.path.join(path, pdfDetailedFilename)
            pdf = self.client["SoftLayer_Billing_Invoice"].getPdfDetailed(id=invoiceId)
            with open(fName, "wb") as pdfFile:
                pdfFile.write(pdf.data)
            ret['fileName'] = pdfDetailedFilename
        except:
            ret['err'] = sys.exc_info()[0]
            #print("downloadInvoicePdfDetailed Unexpected error:", ret['err'])
        return ret

    def downloadInvoiceExcel(self, invoiceId, path=''):
        ret = { 'err': '', 'fileName': '' }
        try:
            xlsFilename = self.client["SoftLayer_Billing_Invoice"].getXlsFilename(id=invoiceId)
            fName = os.path.join(path, xlsFilename)
            pdf = self.client["SoftLayer_Billing_Invoice"].getExcel(id=invoiceId)
            with open(fName, "wb") as pdfFile:
                pdfFile.write(pdf.data)
            ret['fileName'] = xlsFilename
        except:
            ret['err'] = sys.exc_info()[0]
            #print("downloadInvoiceExcel Unexpected error:", ret['err'])
        return ret

    # get recurring report by input month
    def getRecurringInvoice(self, date=None, downloadReport=False, reportPath=''):
        ret = {
            'account': '',
            'accountId': '',
            'invoiceId': [],
            'pdfReport': [],
            'pdfDetailReport': [],
            'excelReport': [],
            'err': [],
            'totalAmount': 0.0,
        }
        for account in self.getBrandAllOwnedAccounts():
            print('>> account: {} ({})'.format(account['companyName'], account['id']))
            ret['account'] = account['companyName']
            ret['accountId'] = account['id']
            # there may exist multiple recurring invoice in one month, so it need add up all those invoices?
            totalAmount = 0.0
            for invoice in account['invoices']:
                createDate = dateparser(invoice['createDate']).astimezone() # convert to utc time
                if invoice['typeCode'] == 'RECURRING':  # filter for recurring type
                    if date == None or (createDate.year == date.year and createDate.month == date.month):   # filter by date
                        print('>>>> invoice: {} ({})'.format(invoice['id'], createDate.strftime('%Y-%m-%d')))
                        ret['invoiceId'].append(invoice['id'])
                        
                        # get SoftLayer_Billing_Invoice
                        invoiceTotalAmount = float(self.client["SoftLayer_Billing_Invoice"].getInvoiceTotalAmount(id=invoice['id']))
                        print('>>>> sub total amount: {}'.format(invoiceTotalAmount))
                        totalAmount += invoiceTotalAmount

                        # debug
                        # print(invoice)

                        # download the report
                        if downloadReport == True:
                            # I can't tell why some pdf summary may not exist and it would raise exception in certain case; details version seems always exist.
                            d1 = self.downloadInvoicePdf(invoice['id'], reportPath) # same as pdf summary from portal site
                            if len(d1['fileName']) > 0:
                                print('>>>> PDF invoice: {}'.format(d1['fileName']))
                                ret['pdfReport'].append(d1['fileName'])
                            else:
                                print('>>>> get PDF invoice failed: {}'.format(d1['err']))
                                ret['err'].append(d1['err'])
                            d2 = self.downloadInvoicePdfDetailed(invoice['id'], reportPath) # same as pdf details from portal site
                            if len(d2['fileName']) > 0:
                                print('>>>> PDF invoice details: {}'.format(d2['fileName']))
                                ret['pdfDetailReport'].append(d2['fileName'])
                            else:
                                print('>>>> get PDF invoice details failed: {}'.format(d2['err']))
                                ret['err'].append(d2['err'])
                            d3 = self.downloadInvoiceExcel(invoice['id'], reportPath)   # same as excel from portal site (it's the most viewable version with details)
                            if len(d3['fileName']) > 0:
                                print('>>>> Excel invoice: {}'.format(d3['fileName']))
                                ret['excelReport'].append(d3['fileName'])
                            else:
                                print('>>>> get Excel invoice failed: {}'.format(d3['err']))
                                ret['err'].append(d3['err'])

                        '''
                        # list items
                        # The item is base components (i.e. flavor vm set would divided into different invoice items: cpu, ran and disk ...)
                        # It's very hard to resample these data as vm flavor based.
                        # Also, it's hard to identiy each component's usage in it, because of poor documents. So this part is been skipped for now ...
                        # It seem like that there is no method to retrieve more usage details in this invoice item, where the result should be as same as above pdf/excel report.
                        getItemMask = 'mask[location,billingItem,category,product]'
                        getItemFilter = { 'items': {} }
                        items = self.client["SoftLayer_Billing_Invoice"].getItems(id=invoice['id'], mask=getItemMask, filter=getItemFilter, iter=True)
                        ti = 0
                        for item in items:
                            print('>>>> debug items ({}): {}'.format(ti, json.dumps(item)))
                            ti = ti + 1
                        '''

            print('>> total amount: {}'.format(totalAmount))
            ret['totalAmount'] = totalAmount

        return ret

    # What we need is to collect one final invoice for last month, but their design is based on each invoice items.
    # (e.g. there would mutiple invoice items for one month)
    # It seems like createDate is the only key to filter for invoice date...
    # Suppose recurring invoice created in this month means it's used at last month.
    def getLastRecurringInvoice(self, downloadReport=False, reportPath=''):
        currentDay = datetime.datetime.utcnow().date()
        print('== get last invoice at {}'.format(currentDay.strftime('%Y-%m')))
        return self.getRecurringInvoice(currentDay, downloadReport, reportPath)

    def getNextInvoice(self, downloadReport=False, reportPath=''):
        ret = {
            'account': '',
            'accountId': '',
            'invoiceId': [],
            'pdfReport': [],
            'pdfDetailReport': [],
            'excelReport': [],
            'err': [],
            'totalAmount': 0.0,
        }
        for account in self.getBrandAllOwnedAccounts(False):
            print('>> account: {} ({})'.format(account['companyName'], account['id']))
            ret['account'] = account['companyName']
            ret['accountId'] = account['id']
            
            # todo ...
            # for now, it's unable to get account info from brand account
            nextInvoiceTotalAmount = self.client["SoftLayer_Account"].getNextInvoiceTotalAmount(id=account['id'])
            print('>>>> next total amount: {}'.format(nextInvoiceTotalAmount))

        return ret
