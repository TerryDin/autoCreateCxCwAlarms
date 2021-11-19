# 自动创建定制化CloudWatch告警方案  —— AWS CLI部署方式
如需使用AWS 控制台的方式进行部署，请参考AWS中文官方博客：《自动创建定制化 CloudWatch 告警方案 —— AWS控制台部署方式》
<br>
<br>
WorkSpace: dir "autoCreateCxCw"    <br>
```
anqdian@3c22fb7680e6 autoCreateCxCw % tree ./
./
├── Lambda1-ALB
│   ├── Deploy.ps1
│   ├── Truncate_Lambda
│   ├── index.py
│   ├── requirements.txt
│   └── setup.cfg
├── Lambda1-EBS
│   ├── Deploy.ps1
│   ├── index.py
│   ├── requirements.txt
│   └── setup.cfg
├── Lambda1-EC
│   ├── Deploy.ps1
│   ├── index.py
│   ├── requirements.txt
│   └── setup.cfg
├── Lambda1-EMR
│   ├── Deploy.ps1
│   ├── index.py
│   ├── requirements.txt
│   └── setup.cfg
├── Lambda1-ES
│   ├── Deploy.ps1
│   ├── index.py
│   ├── requirements.txt
│   └── setup.cfg
├── Lambda1-NLB
│   ├── Deploy.ps1
│   ├── index.py
│   ├── requirements.txt
│   └── setup.cfg
├── Lambda1-RDS
│   ├── Deploy.ps1
│   ├── Truncate_Lambda
│   ├── index.py
│   ├── requirements.txt
│   └── setup.cfg
├── Lambda2
│   ├── Deploy.ps1
│   ├── SNSSubscribtion-pytzLayer.zip
│   ├── assumeRolePolicyDocument.json
│   ├── index.py
│   ├── python
│   │   ├── changeAlarmToLocalTimeZone.py
│   │   ├── pytz
│   │   │   ├── __init__.py
│   │   │   ├── ...
│   │   └── pytz-2021.1.dist-info
│   │       ├── ...
│   ├── requirements.txt
│   └── setup.cfg
└── README.md
```
<br>
<br>


部署指引
* 1. 创建定制化告警信息推送端 - SNS 2    <br>
SNS 2用于将定制化的告警通知发生给相关的团队。    <br>
```
    aws sns create-topic --name <To-DBA_team>    /** 不能以.fifo结尾 */
    aws sns subscribe --topic-arn <arn:aws:sns:us-west-2:532134256174:To-DBA_team> --protocol <email> --notification-endpoint <anqdian@amazon.com>    /** 等待邮箱确认 */
```


* 2. 创建定制化告警信息处理脚本 - Lambda 2    <br>
Lambda 2用于针对自动创建监控的告警信息 进行定制化。    <br>

> 创建执行Lambda的IAM角色：    <br>
```
    anqdian@3c22fb7680e6 autoCreateCxCw % cd ./Lambda2

    aws iam create-role --role-name <lambdaExecRole-autoCreateCxCwAlarms_RDS> --description <"Lambda execution role for Auto create customized CloudWatch alarms for RDS. "> --assume-role-policy-document <file://assumeRolePolicyDocument.json>
```

> Attach权限策略：    <br>
```
    aws iam attach-role-policy --role-name <lambdaExecRole-autoCreateCxCwAlarms_RDS> --policy-arn <arn:aws:iam::aws:policy/AmazonRDSFullAccess> --policy-arn <arn:aws:iam::aws:policy/AmazonEC2FullAccess>
```

> 创建Lambda layer：    <br>

安装PyTZ library，用于本地化时区。    <br>
```
    anqdian@3c22fb7680e6 Lambda2 % mkdir python
    anqdian@3c22fb7680e6 Lambda2 % /usr/bin/pip3 install -t ./python pytz
    anqdian@3c22fb7680e6 Lambda2 % zip -r SNSSubscribtion-pytzLayer.zip ./python/*

    aws lambda publish-layer-version --layer-name <customizedAlarms-RDS_DatabaseConnections> --description <"Customize CloudWatch alarms for RDS - DatabaseConnections. "> --compatible-runtimes python3.8 --zip-file <fileb://SNSSubscribtion-pytzLayer.zip>
```
在刚创建的python目录下，创建changeAlarmToLocalTimeZone.py文件，添加以下内容，并进行打包：
```
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
```
```
anqdian@3c22fb7680e6 autoCreateCxCw % zip -r SNSSubscribtion-pytzLayer.zip ./python/*

aws lambda publish-layer-version --layer-name <customizedAlarms-RDS_DatabaseConnections> --description <"Customize CloudWatch alarms for RDS - DatabaseConnections. "> --compatible-runtimes python3.8 --zip-file <fileb://SNSSubscribtion-pytzLayer.zip>
```

> Powershell on Mac

下载Powershell，选择MacOS 10.13+ <br>
    https://github.com/PowerShell/PowerShell <br>
安装Powershell on Mac，需要在 系统偏好设置 → 安全性与隐私，允许安装Powershell。 <br>
安装AWS工具模块、AWS CLI和升级URLlib <br>
    https://docs.aws.amazon.com/zh_cn/powershell/latest/userguide/pstools-getting-set-up-linux-mac.html <br>
```
# Windows: 
# [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
```
```
# 启动Powershell: 
pwsh
Install-Module -Name AWS.Tools.Installer -Force
Install-Module -Name AWS.Tools.Common
Install-Module -Name AWS.Tools.Lambda,AWS.Tools.SecurityToken
Install-Module AWSPowerShell
Install-Module AWSLambdaPSCore
```
```
pip install --upgrade "urllib3==1.26" awscli
```

> 部署Lambda 2：    <br>

准备以下4个文件：Deploy.ps1、index.py、requirements.txt、setup.cfg，将这4个文件放在单独的文件夹《autoCreateCxCw_RDS-Lambda2》。 <br>
在Powershell当中运行Deploy.ps1，部署Lambda。 <br>
```
<Deploy.ps1>

Set-DefaultAWSRegion -Region <us-west-2>
Set-Location -Path $PSScriptRoot

$ZipFileName = 'lambda2-autoCreateCxCw.zip'


Write-Host -Object 'Restoring dependencies ...'
pip3 install -r $PSScriptRoot/requirements.txt -t $PSScriptRoot/


Write-Host -Object 'Compressing files ...'
Get-ChildItem -Recurse | ForEach-Object -Process {
  $NewPath = $PSItem.FullName.Substring($PSScriptRoot.Length + 1)
  zip -u "$PSScriptRoot/$ZipFileName" $NewPath
# Windows:
# Compress-Archive -Path $NewPath -Update -DestinationPath "$PSScriptRoot\$ZipFileName"
}


Write-Host -Object 'Deploying Lambda function'
$Function = @{
  FunctionName = 'CustomizeCloudWatchAlarmsNotifications-RDS_DatabaseConnections'
  Runtime = 'python3.8'
  Description = 'Customize CloudWatch alarms notification for RDS - DatabaseConnections. '
  ZipFilename = $ZipFileName
  Handler = 'index.lambda_handler'
  Role = '<arn:aws:iam::532134256174:role/lambdaExecRole-autoCreateCxCwAlarms_RDS>'
  Environment_Variable = @{
    NotificationSNSTopic = '<arn:aws:sns:us-west-2:532134256174:To-DBA_team>'
    TimeZoneCode = 'Asia/Hong_Kong'
    TimezoneInitial = 'UTC+8'
  # CHIME_WEBHOOK = 'https://hooks.chime.aws/incomingwebhooks/3c8fd66f-6e40-4375-9fe8-0ba6a57cb375?token=aWVuczdtTUd8MXxCZC05SmNIZ3RqUFMydXpydllNTUx2em15WU5YZVNrX0ZodWc3THljdFg0'
  }
  MemorySize = 512
  Timeout = 60
  Layer = "<arn:aws:lambda:us-west-2:532134256174:layer:customizedAlarms-RDS_DatabaseConnections:1>"
}

Remove-LMFunction -FunctionName $Function.FunctionName -Force
Publish-LMFunction @Function


Write-Host -Object 'Deployment completed' -ForegroundColor Green
```
```
<index.py>

import boto3
import os
from changeAlarmToLocalTimeZone import *

#Get SNS Topic ARN from Environment variables
NotificationSNSTopic = os.environ['NotificationSNSTopic']

#Get timezone corresponding to your localTimezone from Environment variables
timezoneCode = os.environ['TimeZoneCode']

#Get Your local timezone Initials, E.g UTC+2, IST, AEST...etc from Environment variables
localTimezoneInitial=os.environ['TimezoneInitial']

#Get SNS resource using boto3
SNS = boto3.resource('sns')

#Specify the SNS topic to push message to by ARN
platform_endpoint = SNS.PlatformEndpoint(NotificationSNSTopic)

def lambda_handler(event, context):

    #Call Main function
    changeAlarmToLocalTimeZone(event,timezoneCode,localTimezoneInitial,platform_endpoint)
    
    #Print All Available timezones
    #getAllAvailableTimezones()
    
    #search if Timezone/Country exist
    #searchAvailableTimezones('sy')
```
```
<requirements.txt>

requests
```
```
<setup.cfg>

[install]
prefix=
```
```
    anqdian@3c22fb7680e6 Lambda2 % pwsh
    anqdian@3c22fb7680e6 Lambda2 % ./Deploy.ps1
```


* 3. 定制化告警信息 - SNS 1    <br>
SNS 1用于接收告警信息，并转发到Lambda 2对告警通知进行定制化。    <br>
```
    aws sns create-topic --name <customizedAlarmAction-RDS_DatabaseConnections>    /** 不能以.fifo结尾 */
    aws sns subscribe --topic-arn <arn:aws:sns:us-west-2:532134256174:customizedAlarmAction-RDS_DatabaseConnections> --protocol lambda --notification-endpoint <arn:aws:lambda:us-west-2:532134256174:function:CustomizeCloudWatchAlarmsNotifications-RDS_DatabaseConnections>
```


* 4. 自动创建监控告警 - Lambda 1    <br>
Lambda 1 用于为指定的AWS托管服务下所有的实例 自动创建特定的监控告警。    <br>

> 部署Lambda 1

准备以下4个文件：Deploy.ps1、index.py、requirements.txt、setup.cfg，将这4个文件放在单独的文件夹《autoCreateCxCw_RDS-Lambda1》。 <br>
在Powershell当中运行Deploy.ps1，部署Lambda。 <br>
```
<Deploy.ps1>

Set-DefaultAWSRegion -Region <us-west-2>
Set-Location -Path $PSScriptRoot

$ZipFileName = 'lambda1-autoCreateCxCw.zip'


Write-Host -Object 'Restoring dependencies ...'
pip3 install -r $PSScriptRoot/requirements.txt -t $PSScriptRoot/


Write-Host -Object 'Compressing files ...'
Get-ChildItem -Recurse | ForEach-Object -Process {
  $NewPath = $PSItem.FullName.Substring($PSScriptRoot.Length + 1)
  zip -u "$PSScriptRoot/$ZipFileName" $NewPath
# Windows: 
# Compress-Archive -Path $NewPath -Update -DestinationPath "$PSScriptRoot\$ZipFileName"
}


Write-Host -Object 'Deploying Lambda function'
$Function = @{
  FunctionName = 'AutoCreateCloudWatchAlarms-RDS_DatabaseConnections'
  Runtime = 'python3.8'
  Description = 'Auto create customized CloudWatch alarms for RDS - DatabaseConnections. '
  ZipFilename = $ZipFileName
  Handler = 'index.handler'
  Role = '<arn:aws:iam::532134256174:role/lambdaExecRole-autoCreateCxCwAlarms_RDS>'
  Environment_Variable = @{
    MetricName = 'DatabaseConnections'
    MaxItems = '3'
    SNS_topic_suffix = 'RDS_DatabaseConnections'
    # CHIME_WEBHOOK = 'https://hooks.chime.aws/incomingwebhooks/3c8fd66f-6e40-4375-9fe8-0ba6a57cb375?token=aWVuczdtTUd8MXxCZC05SmNIZ3RqUFMydXpydllNTUx2em15WU5YZVNrX0ZodWc3THljdFg0'
  }
  MemorySize = 512
  Timeout = 60
}

Remove-LMFunction -FunctionName $Function.FunctionName -Force
Publish-LMFunction @Function


Write-Host -Object 'Deployment completed' -ForegroundColor Green
```
<index.py> <br>
笔者对RDS、ElasticSearch、ElastiCache、EMR、ELB、EBS等AWS常用服务都进行了适配。例如，需要为RDS实例的CPU利用率创建自动告警，则应完成以下两步： <br>
1. 可使用《RDS - CPUUtilization》的模板作为Lambda1 - index.py里面的内容、并确认校正当中指定的告警阈值； <br>
2. 在上述Lambda1 - Deploy.ps1 - Environment_Variable - MetricName环境变量中，指定对应的CloudWatch告警指标名称（MetricName = 'CPUUtilization'）。 <br>

AWS部分常用服务的自动创建告警Lambda代码模板详见本github repo。 <br>
建议先将<Prepare target RDS list>代码段中，最大创建RDS CloudWatch alarms的数量 调整为2，作为全面铺开本监控告警方案之前的效果实测。 <br>
    
``` 
<requirements.txt>

requests
```
```
<setup.cfg>

[install]
prefix=
```
```
    anqdian@3c22fb7680e6 Lambda1-RDS % pwsh
    anqdian@3c22fb7680e6 Lambda1-RDS % ./Deploy.ps1
```


* 5. 自动创建监控告警 - CloudWatch定时任务    <br>
创建CloudWatch定时任务，定时调用Lambda 1 创建监控告警。    <br>
```
    aws events put-rule --name <AutoCreateCloudWatchAlarms> --description <"Scheduler to run Lambda function <AutoCreateCloudWatchAlarms> every 1 min. "> --schedule-expression "rate(1 minute)" --state <ENABLED>
    aws events put-targets --rule <AutoCreateCloudWatchAlarms> --targets <"Id"="1","Arn"="arn:aws:lambda:us-west-2:532134256174:function:AutoCreateCloudWatchAlarms-RDS_DatabaseConnections">
```
