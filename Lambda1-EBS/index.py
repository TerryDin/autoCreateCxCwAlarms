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

EBS_MetricName = os.environ['MetricName']
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
    CW_filteredIterator = CW_iterator.search("MetricAlarms[?MetricName==`"+EBS_MetricName+"` && Namespace==`AWS/EBS`]")
    

#   Prepare target EBS list
    EBS_client = boto3.client('ec2')
    EBS_paginator = EBS_client.get_paginator('describe_volumes')
    EBS_iterator = EBS_paginator.paginate(
        PaginationConfig={
            # 最大创建EBS CloudWatch alarms的数量
            'MaxItems': MaxItems
        }
    )

#   Prepare EBS full list
    print('------')
    print('EBS full list:')
    EBS_rawList = []
    EBS_idList = []
    for EBS_response in EBS_iterator:
        EBS_rawList.extend(EBS_response['Volumes'])
        for ec2_att in EBS_rawList:
            if ec2_att['VolumeType'][0:2] != 'io':
                for ebs_volume in ec2_att['Attachments']:
                    print(ebs_volume['VolumeId'])
                    EBS_idList.append(ebs_volume['VolumeId'])


#   Prepare EBS ignore list: 筛选出已经创建对应监控告警的EBS磁盘实例
    print('------')
    print('EBS ignore list:')
    EBS_ignoreList = []
    for alarm in CW_filteredIterator:
#       判断已有的监控告警是否为正准备创建的监控告警
        if alarm['MetricName'] == EBS_MetricName:
            for dimension in alarm["Dimensions"]:
                if dimension["Name"] == "VolumeId":
                    print(dimension["Value"])
                    EBS_ignoreList.append(dimension["Value"])


#   Drop CloudWatch alarm cascade: 
    print('------')
    for cw in EBS_ignoreList:
        if is_existed_inList(cw, EBS_idList):
            print('Dropping CloudWatch alarm "EBS_'+EBS_MetricName+'" for: '+cw)
            CWalarms = CW_client.delete_alarms(
                AlarmNames=['EBS_'+EBS_MetricName+'-'+cw]
            )
            print('Dropped CloudWatch alarm "EBS_'+EBS_MetricName+'" for: '+cw)


#   Create customized CloudWatch alarms auto: 
    print ('')
    for ebs_vol in EBS_idList:
#       预先定义SNS topic suffix，不同的CloudWatch告警通知会发送到不同的SNS topic
        print('------')
#       判断是否并未创建对应的监控告警
        if is_existed_inList(ebs_vol, EBS_ignoreList):
            print('------')
            print('EBS ID: '+ebs_vol)
            print('Creating CloudWatch alarm "EBS_'+EBS_MetricName+'" for: '+ebs_vol)
#           创建监控告警
            CWalarms = CW_client.put_metric_alarm(
                AlarmName='EBS_'+EBS_MetricName+'-'+ebs_vol, 
                AlarmDescription='Auto-created customized CloudWatch Alarm <EBS_'+EBS_MetricName+'>',
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
                MetricName=EBS_MetricName,
                Namespace="AWS/EBS",
                Statistic='Minimum',
                # 'SampleCount'|'Average'|'Sum'|'Minimum'|'Maximum'
#                ExtendedStatistic='p100',
                Dimensions=[
                    {
                        'Name': 'VolumeId',
                        'Value': ebs_vol
                    },
                ],
#                print(ebs_name['LoadBalancerArn'].split('/',1)[1])
                Period=60,
#                Unit='Seconds',
                # 'Seconds'|'Microseconds'|'Milliseconds'|'Bytes'|'Kilobytes'|'Megabytes'|'Gigabytes'|'Terabytes'|'Bits'|'Kilobits'|'Megabits'|'Gigabits'|'Terabits'|'Percent'|'Count'|'Bytes/Second'|'Kilobytes/Second'|'Megabytes/Second'|'Gigabytes/Second'|'Terabytes/Second'|'Bits/Second'|'Kilobits/Second'|'Megabits/Second'|'Gigabits/Second'|'Terabits/Second'|'Count/Second'|'None'
                EvaluationPeriods=15,
                DatapointsToAlarm=15,
                Threshold=50,
                ComparisonOperator='LessThanOrEqualToThreshold',
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
                        'Key': str('EBS_'+EBS_MetricName),
                        'Value': 'autocreated'
                    },
                ],
#                ThresholdMetricId='string'
            )

#           为该EBS磁盘标记CWalarm-BurstBalance标签
            EBS_tags = EBS_client.create_tags(
                Resources = [ebs_vol],
                Tags=[
                    {
                        'Key': str('CWalarm-'+EBS_MetricName),
                        'Value': 'enabled'
                    },
                ]
            )
            print('Added tag "CWalarm-'+EBS_MetricName+'" to: '+ebs_vol)

            print('Created CloudWatch alarm "EBS_'+EBS_MetricName+'" for: '+ebs_vol)
            print()
        else: 
            print('No CloudWatch alarm created for: '+ebs_vol)
    return {
        'statusCode': 200,
        'body': json.dumps('Mission Complete!')
    }


#run_command('/var/task/aws --version')
#run_command('ls -l')