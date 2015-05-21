from mpl_toolkits.mplot3d import Axes3D
from matplotlib import cm
from matplotlib.ticker import LinearLocator, FormatStrFormatter
import matplotlib.pyplot as plt
import numpy as np

import urllib2
import json
import time
from azure.storage import *

# Default settings for Azure ML
storage_account_name = "accname" # Replace this with your Azure Storage Account name
storage_account_key = "acckey" # Replace this with your Azure Storage Key
storage_container_name = "ctnname" # Replace this with your Azure Storage Container name

input_file = "range.csv" # Replace this with the location of your input file
output_file = "myresults.csv" # Replace this with the location you would like to use for your output file
input_blob_name = "mydatablob.csv" # Replace this with the name you would like to use for your Azure blob; this needs to have the same extension as the input file 
api_key = "yourapikey"  # Repalce this with your web service api key
url = "https://yourrequestURI" # Replace this with your web service batch api request URI

# Default settings for Chiller input condition ranges
header = 'kW,chFlow,chT2,coT1,chT1\n'

kwDefault = 300.0       # 0 power
chFlowDefault = 3000.0    # 1 flow rate of water
chT2Default = 10.0      # 2 temperature of water after going through the tubes in rooms
coT1Default = 27.5      # 3 temperature of water which was used to cool down the chiller
chT1Default = 8.5        # 4 temperature of water before going through the tubes in rooms

load = 3800 * 4.5       # load is the product of flow and deltaT. The assumption here is load will not change.

defaultVals = [kwDefault, chFlowDefault, chT2Default, coT1Default, chT1Default]


maxRangeX = 4600
minRangeX = 1000
stepX = 100
indX = 1


maxRangeY = 11.1
minRangeY = 8
stepY = 0.1
indY = 4


# Generate input file
RangeX = np.arange(minRangeX, maxRangeX, stepX)
RangeY = np.arange(minRangeY, maxRangeY, stepY)

RangeXm, RangeYm = np.meshgrid(RangeX, RangeY)

csv_file = open("range.csv", "w")

csv_file.write(header)

for i in xrange(0, RangeY.size):
    for j in xrange(0, RangeX.size):
        rowData = []
        for ind in xrange(0, len(defaultVals)):
            if (ind == indX):
                rowData.append(RangeXm[i][j])
            elif (ind == indY):
                rowData.append(RangeYm[i][j])
            elif (ind == 2): # chT2 calculated based on constant load
                outV = RangeYm[i][j] + (load / RangeXm[i][j])
                rowData.append(outV)
            else:
                rowData.append(defaultVals[ind])
            csv_file.write("%f" % rowData[ind])
            if (ind != (len(defaultVals) - 1)):
                csv_file.write(",")
            else:
                csv_file.write("\n")

csv_file.close()

# Submit to CloudML WebService
blob_service = BlobService(account_name=storage_account_name, account_key=storage_account_key)

print("Uploading the input to blob storage...")
data_to_upload = open(input_file, "r").read()
blob_service.put_blob(storage_container_name, input_blob_name, data_to_upload, x_ms_blob_type="BlockBlob")
input_blob_path = "/" + storage_container_name + "/" + input_blob_name

print("Submitting the BES job...")
connection_string = "DefaultEndpointsProtocol=https;AccountName=" + storage_account_name + ";AccountKey=" + storage_account_key
payload =  {
            "Input": {
                "ConnectionString": connection_string,
                "RelativeLocation": input_blob_path
                }
            }

body = str.encode(json.dumps(payload))
headers = { "Content-Type":"application/json", "Authorization":("Bearer " + api_key)}
req = urllib2.Request(url, body, headers) 
response = urllib2.urlopen(req)
result = response.read()
job_id = result[1:-1] # remove the enclosing double-quotes

url2 = url + "/" + job_id

while True:
    req = urllib2.Request(url2, headers = { "Authorization":("Bearer " + api_key) })
    response = urllib2.urlopen(req)    
    result = json.loads(response.read())
    status = result["StatusCode"]
    if (status == 0):
        print("Not started...")
    elif (status == 1):
        print("Running...")
    elif (status == 2):
        print("Failed!")
        print("Error details: " + result["Details"])
        break
    elif (status == 3):
        print("Cancelled!")
        break
    elif (status == 4):
        print("Finished!")
        result_blob_location = result["Result"]
        sas_token = result_blob_location["SasBlobToken"]
        base_url = result_blob_location["BaseLocation"]
        relative_url = result_blob_location["RelativeLocation"]
        url3 = base_url + relative_url + sas_token
        response = urllib2.urlopen(url3)
        with open(output_file, "w+") as f:
           f.write(response.read())
           print("The results have been written to the file " + output_file)
        break
    time.sleep(1) # wait one second

# Process output file from CloudML

ous = open(output_file, "r")
resArr = []
bFirst = True
for line in ous:
    if len(line) > 5:           # 5 means this is not an empty line. This is a bug in CloudML which will return empty lines
        fields = line.split(",")
        prid = fields[len(defaultVals)]        # The prediction lies in the extra column of returned csv file
        if bFirst:
            bFirst = False
            continue
        ppc = float(prid)
        
        # Calculate the efficiency here, comment these lines to get power graph instead of efficiency graph
##        chT1 = float(fields[4])
##        chT2 = float(fields[2])
##        flow = float(fields[1])
##        ppc = ppc / ((chT2 - chT1) * flow * 4.187 / (3.516 * 60))
        
        resArr.append(ppc)

# For demo only
draw_file = open("draw.txt", "w")

# list of list
ll = []
for i in xrange(0, len(resArr), RangeX.size):
    ll.append(resArr[i:i + RangeX.size])
    numbs = resArr[i:i + RangeX.size]
    for j in xrange(0, len(numbs)):
        draw_file.write(str(numbs[j]))
        if j != (len(numbs) - 1):
            draw_file.write(",")
        else:
            draw_file.write("\n")

draw_file.close()

Z = np.array(ll)


# Plot 3-D figure

X = RangeXm
Y = RangeYm

fig = plt.figure()
ax = fig.gca(projection='3d')
surf = ax.plot_surface(X, Y, Z, rstride=1, cstride=1, cmap=cm.coolwarm,
        linewidth=0, antialiased=False)

#ax.set_zlim(-1.01, 1.01)

#ax.zaxis.set_major_locator(LinearLocator(10))
#ax.zaxis.set_major_formatter(FormatStrFormatter('%.02f'))

fig.colorbar(surf, shrink=0.5, aspect=5)

plt.show()
        
