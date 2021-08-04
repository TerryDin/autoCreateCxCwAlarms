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

EMR_MetricName = os.environ['MetricName']
MaxItems = os.environ['MaxItems']
SNS_topic_suffix = os.environ['SNS_topic_suffix']

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def is_existed_inList(target, list):
    if target in list:
        return False
    else:
        return True


def map_maxVal(instanceSize): 
    if instanceSize == 'large':
        return 1000
    if instanceSize == 'xlarge':
        return 2000
    if instanceSize == '2xlarge':
        return 3000
    if instanceSize == '4xlarge':
        return 5000
    if instanceSize == '8xlarge':
        return 10000
    if instanceSize == '12xlarge':
        return 15000
    if instanceSize == '16xlarge':
        return 20000
    if instanceSize == '24xlarge':
        return 30000
    if instanceSize == 'small':
        return 45
    if instanceSize == 'medium':
        return 90
    else:
        return 999


def get_instanceFamily(instanceFamily):
    if instanceFamily == 't2':
        return False
    if instanceFamily == 't3':
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
    CW_filteredIterator = CW_iterator.search("MetricAlarms[?MetricName==`"+EMR_MetricName+"` && Namespace==`AWS/ElasticMapReduce`]")
    

#   Prepare target EMR list
    EMR_client = boto3.client('emr')
    EMR_paginator = EMR_client.get_paginator('list_clusters')
    EMR_iterator = EMR_paginator.paginate(
        PaginationConfig={
            # 最大创建EMR CloudWatch alarms的数量
            'MaxItems': MaxItems
        }
    )

#   Prepare EMR full list
    print('------')
    print('EMR full list:')
    EMR_rawList = []
    EMR_arnList = []
    EMR_idList = []
    EMR_nameList = []
    for EMR_response in EMR_iterator:
        EMR_rawList.extend(EMR_response['Clusters'])
        for EMR_cluster in EMR_response['Clusters']:
            if EMR_cluster['Status']['State'][0:8] != 'TERMINAT':
                print(EMR_cluster['Id'])
                EMR_idList.append(EMR_cluster['Id'])
                EMR_arnList.append(EMR_cluster['ClusterArn'])
                EMR_nameList.append(EMR_cluster['Name'])


#   Prepare EMR ignore list: 筛选出已经创建对应监控告警的EMR数据库实例
    print('------')
    print('EMR ignore list:')
#    alarm = cloudwatch.Alarm('name')
    EMR_ignoreList = []
    for alarm in CW_filteredIterator:
#       判断已有的监控告警是否为正准备创建的监控告警
        if alarm['MetricName'] == EMR_MetricName:
            for dimension in alarm["Dimensions"]:
#                print(dimension)
                if dimension["Name"] == "JobFlowId":
                    EMR_ignoreList.append(dimension["Value"])
                    print(dimension["Value"])


#   Drop CloudWatch alarm cascade: 
    print('------')
    for cw in EMR_ignoreList:
        if is_existed_inList(cw, EMR_idList):
            print('Dropping CloudWatch alarm "EMR_'+EMR_MetricName+'" for: '+cw)
            CWalarms = CW_client.delete_alarms(
                AlarmNames=['EMR_'+EMR_MetricName+'-'+cw]
            )
            print('Dropped CloudWatch alarm "EMR_'+EMR_MetricName+'" for: '+cw)


#   Create customized CloudWatch alarms auto: 
    print ('')
    for emr_arn in EMR_arnList:
#       预先定义SNS topic suffix，不同的CloudWatch告警通知会发送到不同的SNS topic
        emr_id = emr_arn.split('/', 1)[1]
        print('------')
#       判断是否并未创建对应的监控告警
        if is_existed_inList(emr_id, EMR_ignoreList):
            print('------')
            print('EMR ID: '+emr_id)
            print('Creating CloudWatch alarm "EMR_'+EMR_MetricName+'" for: '+emr_id)
#           创建监控告警
            CWalarms = CW_client.put_metric_alarm(
                AlarmName='EMR_'+EMR_MetricName+'-'emr_id, 
                AlarmDescription='Auto-created customized CloudWatch Alarm <EMR_'+EMR_MetricName+'>',
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
                MetricName=EMR_MetricName,
                Namespace="AWS/ElasticMapReduce",
                Statistic='Maximum',
                # 'SampleCount'|'Average'|'Sum'|'Minimum'|'Maximum'
#                ExtendedStatistic='p100',
                Dimensions=[
                    {
                        'Name': 'JobFlowId',
                        'Value': emr_id
                    },
                ],
                Period=60,
#                Unit='Seconds',
                # 'Seconds'|'Microseconds'|'Milliseconds'|'Bytes'|'Kilobytes'|'Megabytes'|'Gigabytes'|'Terabytes'|'Bits'|'Kilobits'|'Megabits'|'Gigabits'|'Terabits'|'Percent'|'Count'|'Bytes/Second'|'Kilobytes/Second'|'Megabytes/Second'|'Gigabytes/Second'|'Terabytes/Second'|'Bits/Second'|'Kilobits/Second'|'Megabits/Second'|'Gigabits/Second'|'Terabits/Second'|'Count/Second'|'None'
                EvaluationPeriods=15,
                DatapointsToAlarm=15,
                Threshold=75,
                ComparisonOperator='GreaterThanOrEqualToThreshold',
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
                        'Key': str('EMR_'+EMR_MetricName),
                        'Value': 'autocreated'
                    },
                ],
#                ThresholdMetricId='string'
            )

#           为该EMR数据库标记CWalarm-HDFSUtilization标签
            EMR_tags = EMR_client.add_tags(
                ResourceId = emr_id,
                Tags=[
                    {
                        'Key': str('CWalarm-'+EMR_MetricName),
                        'Value': 'enabled'
                    },
                ]
            )
            print('Added tag "CWalarm-'+EMR_MetricName+'" to: '+emr_id)

            print('Created CloudWatch alarm "EMR_'+EMR_MetricName+'" for: '+emr_id)
            print()
        else: 
            print('No CloudWatch alarm created for: '+emr_id)
    return {
        'statusCode': 200,
        'body': json.dumps('Mission Complete!')
    }


#run_command('/var/task/aws --version')
#run_command('ls -l')