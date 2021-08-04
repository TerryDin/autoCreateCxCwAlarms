# autoCreateCxCwAlarms
Create Customized CloudWatch Alarms
    <br>
    <br>
WorkSpace: dir <autoCreateCxCw>    <br>
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
<br>
<br>
* 定制化告警信息 - SNS 2    <br>
SNS 2用于将定制化的告警通知发生给相关的团队。    <br>
```
    aws sns create-topic --name <To-DBA_team>    /** 不能以.fifo结尾 */
    aws sns subscribe --topic-arn <arn:aws:sns:us-west-2:532134256174:To-DBA_team> --protocol <email> --notification-endpoint <anqdian@amazon.com>    /** 等待邮箱确认 */
```
<br>
<br>
* 定制化告警信息 - Lambda 2    <br>
Lambda 2用于针对自动创建监控的告警信息 进行定制化。    <br>
<br>
> 创建执行Lambda的IAM角色：    <br>
```
    anqdian@3c22fb7680e6 autoCreateCxCw % cd ./Lambda2

    aws iam create-role --role-name <lambdaExecRole-autoCreateCxCwAlarms_RDS> --description <"Lambda execution role for Auto create customized CloudWatch alarms for RDS. "> --assume-role-policy-document <file://assumeRolePolicyDocument.json>
```
<br>
> Attach权限策略：    <br>
```
    aws iam attach-role-policy --role-name <lambdaExecRole-autoCreateCxCwAlarms_RDS> --policy-arn <arn:aws:iam::aws:policy/AmazonRDSFullAccess> --policy-arn <arn:aws:iam::aws:policy/AmazonEC2FullAccess>
```
<br>
> 创建Lambda layer：    <br>
安装PyTZ library，用于本地化时区。    <br>
```
    anqdian@3c22fb7680e6 Lambda2 % mkdir python
    anqdian@3c22fb7680e6 Lambda2 % /usr/bin/pip3 install -t ./python pytz
    anqdian@3c22fb7680e6 Lambda2 % zip -r SNSSubscribtion-pytzLayer.zip ./python/*

    aws lambda publish-layer-version --layer-name <customizedAlarms-RDS_DatabaseConnections> --description <"Customize CloudWatch alarms for RDS - DatabaseConnections. "> --compatible-runtimes python3.8 --zip-file <fileb://SNSSubscribtion-pytzLayer.zip>
```
<br>
> 部署Lambda 2：    <br>
```
    anqdian@3c22fb7680e6 Lambda2 % pwsh
    anqdian@3c22fb7680e6 Lambda2 % ./Deploy.ps1
```
<br>
<br>
* 定制化告警信息 - SNS 1    <br>
SNS 1用于接收告警信息，并转发到Lambda 2对告警通知进行定制化。    <br>
```
    aws sns create-topic --name <customizedAlarmAction-RDS_DatabaseConnections>    /** 不能以.fifo结尾 */
    aws sns subscribe --topic-arn <arn:aws:sns:us-west-2:532134256174:customizedAlarmAction-RDS_DatabaseConnections> --protocol lambda --notification-endpoint <arn:aws:lambda:us-west-2:532134256174:function:CustomizeCloudWatchAlarmsNotifications-RDS_DatabaseConnections>
```
<br>
<br>
* 自动创建监控告警 - Lambda 1    <br>
Lambda 1 用于为指定的AWS托管服务下所有的实例 自动创建特定的监控告警。    <br>
```
    anqdian@3c22fb7680e6 Lambda1-RDS % pwsh
    anqdian@3c22fb7680e6 Lambda1-RDS % ./Deploy.ps1
```
<br>
<br>
* 自动创建监控告警 - CloudWatch定时任务    <br>
创建CloudWatch定时任务，定时调用Lambda 1 创建监控告警。    <br>
```
    aws events put-rule --name <AutoCreateCloudWatchAlarms> --description <"Scheduler to run Lambda function <AutoCreateCloudWatchAlarms> every 1 min. "> --schedule-expression "rate(1 minute)" --state <ENABLED>
    aws events put-targets --rule <AutoCreateCloudWatchAlarms> --targets <"Id"="1","Arn"="arn:aws:lambda:us-west-2:532134256174:function:AutoCreateCloudWatchAlarms-RDS_DatabaseConnections">
```
