import json
import boto3
import datetime
import pytz
import re
import urllib
import pytz
import re

def searchAvailableTimezones(zone):
    for s in pytz.all_timezones:
        if re.search(zone, s, re.IGNORECASE):
            print('Matched Zone: {}'.format(s))

def getAllAvailableTimezones():
    for tz in pytz.all_timezones:
        print (tz)

def changeAlarmToLocalTimeZone(event,timezoneCode,localTimezoneInitial,platform_endpoint):
    tz = pytz.timezone(timezoneCode)
    #exclude the Alarm event from the SNS records
    AlarmEvent = json.loads(event['Records'][0]['Sns']['Message'])

    #extract event data like alarm name, region, state, timestamp
    alarmName=AlarmEvent['AlarmName']
    descriptionexist=0
    if "AlarmDescription" in AlarmEvent:
        description= AlarmEvent['AlarmDescription']
        descriptionexist=1
    reason=AlarmEvent['NewStateReason']
    region=AlarmEvent['Region']
    state=AlarmEvent['NewStateValue']
    previousState=AlarmEvent['OldStateValue']
    timestamp=AlarmEvent['StateChangeTime']
    Subject= event['Records'][0]['Sns']['Subject']
    alarmARN=AlarmEvent['AlarmArn']
    RegionID=alarmARN.split(":")[3]
    AccountID=AlarmEvent['AWSAccountId']

    #get the datapoints substring
    pattern = re.compile('\[(.*?)\]')
    
    #test if pattern match and there is datapoints
    if pattern.search(reason):
        Tempstr = pattern.findall(reason)[0]

        #get in the message all datapoints timestamps and convert to localTimezone using same format
        pattern = re.compile('\(.*?\)')
        m = pattern.finditer(Tempstr)
        for match in m:
            Tempstr=match.group()
            tempStamp = datetime.datetime.strptime(Tempstr, "(%d/%m/%y %H:%M:%S)")
            tempStamp = tempStamp.astimezone(tz)
            tempStamp = tempStamp.strftime('%d/%m/%y %H:%M:%S')
            reason=reason.replace(Tempstr, '('+tempStamp+')')
    

    #convert timestamp to localTimezone time
    timestamp = timestamp.split(".")[0]
    timestamp = datetime.datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S")
    localTimeStamp = timestamp.astimezone(tz)
    localTimeStamp = localTimeStamp.strftime("%A %B, %Y %H:%M:%S")

    #create Custom message and change timestamps

    customMessage='You are receiving this email because your Amazon CloudWatch Alarm "'+alarmName+'" in the '+region+' region has entered the '+state+' state, because "'+reason+'" at "'+localTimeStamp+' '+localTimezoneInitial +'.'
    
    # Add Console link
    customMessage=customMessage+'\n\n View this alarm in the AWS Management Console: \n'+ 'https://'+RegionID+'.console.aws.amazon.com/cloudwatch/home?region='+RegionID+'#s=Alarms&alarm='+urllib.parse.quote(alarmName)
    
    #Add Alarm Name
    customMessage=customMessage+'\n\n Alarm Details:\n- Name:\t\t\t\t\t\t'+alarmName
    
    # Add alarm description if exist
    if (descriptionexist == 1) : customMessage=customMessage+'\n- Description:\t\t\t\t\t'+description
    customMessage=customMessage+'\n- State Change:\t\t\t\t'+previousState+' -> '+state

    # Add alarm reason for changes
    customMessage=customMessage+'\n- Reason for State Change:\t\t'+reason
 
    # Add alarm evaluation timeStamp   
    customMessage=customMessage+'\n- Timestamp:\t\t\t\t\t'+localTimeStamp+' '+localTimezoneInitial

    # Add AccountID    
    customMessage=customMessage+'\n- AWS Account: \t\t\t\t'+AccountID
    
    # Add Alarm ARN
    customMessage=customMessage+'\n- Alarm Arn:\t\t\t\t\t'+alarmARN

    #push message to SNS topic
    response = platform_endpoint.publish(
        Message=customMessage,
        Subject=Subject,
        MessageStructure='string'
    )
