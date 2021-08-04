from __future__ import print_function
from botocore.exceptions import ClientError
from base64 import b64decode
import subprocess
import logging
import json
import os
import requests
import json
import boto3

ALB_MetricName = os.environ['MetricName']
MaxItems = os.environ['MaxItems']
SNS_topic_suffix = os.environ['SNS_topic_suffix']

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def is_existed_inList(target, list):
    if target in list:
        return False
    else:
        return True


# The 'handler' Python function is the entry point for AWS Lambda function invocations.
def handler(event, context):

    stsClient = boto3.client('sts')
    accountId = stsClient.get_caller_identity().get('Account')
    print('------')
    print('Account: '+accountId)


#   List metrics through the pagination interface
    CW_client = boto3.client('cloudwatch')
    CW_paginator = CW_client.get_paginator('describe_alarms')
    CW_iterator = CW_paginator.paginate()
    CW_filteredIterator = CW_iterator.search("MetricAlarms[?MetricName==`"+ALB_MetricName+"` && Namespace==`AWS/ApplicationELB`]")
    

#   Prepare target ALB list
    appELB_client = boto3.client('elbv2')
    appELB_paginator = appELB_client.get_paginator('describe_load_balancers')
    appELB_iterator = appELB_paginator.paginate(
    PaginationConfig={
            # 最大创建ALB CloudWatch alarms的数量
            # 在产线实测阶段，可将值调整为2
            'MaxItems': MaxItems,
            # 演示分页，最大可以设置成400
            'PageSize': 20
        }
    )


#   Prepare ALB full list
    print('------')
    print('ALB full list:')
    appELB_rawList = []
    appELB_idList = []
    appELB_nameList = []
    for appELB_response in appELB_iterator:
#        'Scheme': 'internet-facing'
#        print(appELB_response['LoadBalancers'])
        appELB_rawList.extend(appELB_response['LoadBalancers'])
    for dict in appELB_rawList:
        for i in dict.items():
            if i[0] == "LoadBalancerArn":
                print(i[1].split('/',3)[2])
                appELB_idList.append(i[1].split('/',1)[1])
                appELB_nameList.append(i[1].split('/',3)[2])

#   Prepare ALB ignore list: 筛选出已经创建对应监控告警的ALB
    print('------')
    print('ALB ignore list:')
    appELB_ignoreList = []
    for alarm in CW_filteredIterator:
#       判断已有的监控告警是否为正准备创建的监控告警
        if alarm['MetricName'] == ALB_MetricName:
            for dimension in alarm["Dimensions"]:
                if dimension["Name"] == ["LoadBalancer"][0]:
                    appELB_ignoreList.append(dimension["Value"])
                    print(dimension["Value"].split('/',2)[1])


#   Drop CloudWatch alarm cascade:
    print('------')
    for cw in appELB_ignoreList:
        if is_existed_inList(cw, appELB_idList):
            print('Dropping CloudWatch alarm "appELB_'+ALB_MetricName+'" for: '+cw.split('/',2)[1])
            CWalarms = CW_client.delete_alarms(
                AlarmNames=['appELB_'+ALB_MetricName+'-'+cw.split('/',2)[1]]
            )
            print('Dropped CloudWatch alarm "appELB_'+ALB_MetricName+'" for: '+cw.split('/',2)[1])


#   Create customized CloudWatch alarms auto: 
    print ('')
    for appELB in appELB_rawList:
#       预先定义SNS topic suffix，不同的CloudWatch告警通知会发送到不同的SNS topic
        print('------')
#       判断是否为appELB，且未创建对应的监控告警
        if is_existed_inList(appELB["LoadBalancerArn"].split('/',1)[1], appELB_ignoreList) & (appELB["LoadBalancerArn"].split('/',1)[1].split('/',1)[0] == 'app'):
            print('------')
            print('ALB name: '+appELB['LoadBalancerName'])
            print('Creating CloudWatch alarm "appELB_'+ALB_MetricName+'" for: '+appELB['LoadBalancerName'])
            CWalarms = CW_client.put_metric_alarm(
                AlarmName='appELB_'+ALB_MetricName+'-'+appELB['LoadBalancerName'], 
                AlarmDescription='Auto-created customized CloudWatch Alarm <appELB_'+ALB_MetricName+'>',
                ActionsEnabled=True,
#                OKActions=[
#                    'string',
#                ],
                AlarmActions=[
                    # 示例，发送到SNS
                    'arn:aws:sns:us-west-2:{}:customizedAlarmAction-{}'.format(accountId,SNS_topic_suffix)
                ], 
#                InsufficientDataActions=[
#                    'string',
#                ],
                MetricName=ALB_MetricName,
                Namespace="AWS/ApplicationELB",
                Statistic='Sum',
                # 'SampleCount'|'Average'|'Sum'|'Minimum'|'Maximum'
#                ExtendedStatistic='p100',
                Dimensions=[
                    {
                        'Name': 'LoadBalancer',
                        'Value': appELB['LoadBalancerArn'].split('/',1)[1]
                    },
                ],
                Period=60,
#                Unit='Seconds',
                # 'Seconds'|'Microseconds'|'Milliseconds'|'Bytes'|'Kilobytes'|'Megabytes'|'Gigabytes'|'Terabytes'|'Bits'|'Kilobits'|'Megabits'|'Gigabits'|'Terabits'|'Percent'|'Count'|'Bytes/Second'|'Kilobytes/Second'|'Megabytes/Second'|'Gigabytes/Second'|'Terabytes/Second'|'Bits/Second'|'Kilobits/Second'|'Megabits/Second'|'Gigabits/Second'|'Terabits/Second'|'Count/Second'|'None'
                EvaluationPeriods=3,
                DatapointsToAlarm=2,
                Threshold=300.0,
                ComparisonOperator='GreaterThanThreshold',
                # 'GreaterThanOrEqualToThreshold'|'GreaterThanThreshold'|'LessThanThreshold'|'LessThanOrEqualToThreshold'|'LessThanLowerOrGreaterThanUpperThreshold'|'LessThanLowerThreshold'|'GreaterThanUpperThreshold'
                TreatMissingData='ignore',
#                EvaluateLowSampleCountPercentile='ignore',
#                Metrics=[
#                    {
#                        'Id': 'string',
#                        'MetricStat': {
#                            'Metric': {
#                                'Namespace': 'string',
#                                'MetricName': 'string',
#                                'Dimensions': [
#                                    {
#                                        'Name': 'string',
#                                        'Value': 'string'
#                                    },
#                               ]
#                            },
#                            'Period': 123,
#                            'Stat': 'string',
#                            'Unit': 'Seconds'|'Microseconds'|'Milliseconds'|'Bytes'|'Kilobytes'|'Megabytes'|'Gigabytes'|'Terabytes'|'Bits'|'Kilobits'|'Megabits'|'Gigabits'|'Terabits'|'Percent'|'Count'|'Bytes/Second'|'Kilobytes/Second'|'Megabytes/Second'|'Gigabytes/Second'|'Terabytes/Second'|'Bits/Second'|'Kilobits/Second'|'Megabits/Second'|'Gigabits/Second'|'Terabits/Second'|'Count/Second'|'None'
#                        },
#                        'Expression': 'string',
#                        'Label': 'string',
#                        'ReturnData': True|False,
#                        'Period': 123
#                    },
#                ],
                Tags=[
                    {
                        'Key': str('appELB_'+ALB_MetricName),
                        'Value': 'autocreated'
                    },
                ],
#                ThresholdMetricId='string'
            )

#           为该ALB标记CWalarm-HTTPCode_Target_5XX_Count标签
            appELB_tags = appELB_client.add_tags(
                ResourceArns=[
                    appELB["LoadBalancerArn"]
                ],
                Tags=[
                    {
                        'Key': str('CWalarm-'+ALB_MetricName),
                        'Value': 'enabled'
                    },
                ]
            )
            print('Added tag "CWalarm-'+ALB_MetricName+'" to: '+appELB["LoadBalancerName"])

            print('Created CloudWatch alarm "appELB_'+ALB_MetricName+'" for: '+appELB["LoadBalancerName"])
            print()
        else: 
            print('No CloudWatch alarm created for: '+appELB["LoadBalancerName"])
    return {
        'statusCode': 200,
        'body': json.dumps('Mission Complete!')
    }

#run_command('/var/task/aws --version')
#run_command('ls -l')