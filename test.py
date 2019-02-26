from slhelper.slhelper import slhelper
import pprint

sl = slhelper(username='{FILL_YOUR_USERNAME}', api_key='{FILL_YOUR_APIKEY}')

pprint.pprint(sl.getPresets(), width=500)