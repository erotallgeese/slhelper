# slhelper

Warper class from python-softlayer to get price information and others.

## Pricing API

To use following api, it only need smallest permission with read only.

* With debug flag on, it would preserve the result from api call to local file as cache to reduce the next call. The cache file is located in slhelper.

### getPresets

* Retrieve each price of vm flavor for each region.
* The real unit is data-center but region. To simplify, there would choose one latest data-center(largest id) for each region. (e.g. there would only keep one dal13 for Dallas)

### getDataTransferPrice

* Retrieve the price about data transfer at each region.
* The real unit is data-center but region. To simplify, there would choose one latest data-center(largest id) for each region. (e.g. there would only keep one dal13 for Dallas)

### getOSPrice

* Retrieve each OS price.
* OS price is same in all region.
* The price tier is provided by cpu cores.

### getStoragePrice

* Retrieve each block storage price for each region.
* To simplify, there would choose for iops 2, which is used for general usage.
* Minimum and maximum size per one block storage is provided.

## SSH API

To use following api, check the permission of your api key.

### getSshKeyList

* Retrieve the ssh key list for this user.

### createSshKey

* It would create RSA 4096 key pair and upload to softlayer.
* The result is the keyid after upload succeed.

## Invoice API

TBD

## Brand API

TBD

## Reference

* <https://softlayer.github.io/reference/>
* <https://softlayer.github.io/python>
* <https://softlayer.github.io/blog/bpotter/going-further-softlayer-api-python-client-part-1/>
* <https://softlayer-python.readthedocs.io/en/latest/api/client.html>