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

RDS_MetricName = os.environ['MetricName']
MaxItems = os.environ['MaxItems']
SNS_topic_suffix = os.environ['SNS_topic_suffix']

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def is_existed_inList(target, list):
    if target in list:
        return False
    else:
        return True


def map_maxConnections(instanceSize): 
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
    CW_filteredIterator = CW_iterator.search("MetricAlarms[?MetricName==`"+RDS_MetricName+"` && Namespace==`AWS/RDS`]")

#   Prepare target RDS list
    RDS_client = boto3.client('rds')
    RDS_paginator = RDS_client.get_paginator('describe_db_instances')
    RDS_iterator = RDS_paginator.paginate(
        PaginationConfig={
            # 最大创建RDS CloudWatch alarms的数量
            'MaxItems': MaxItems,
            # 演示分页，最小20，最大100
            'PageSize': 100
        }
    )

#   Prepare RDS full list
    print('------')
    print('RDS full list:')
    RDS_rawList = []
    RDS_nameList = []
#    RDS_idList = []
    for RDS_response in RDS_iterator:
        RDS_rawList.extend(RDS_response['DBInstances'])
    for dict in RDS_rawList:
        for i in dict.items():
            if i[0] == "DBInstanceIdentifier":
                print(i[1])
                RDS_nameList.append(i[1])
#                RDS_idList.append(i[1].split('/',1)[1])


#   Prepare RDS ignore list: 筛选出已经创建对应监控告警的RDS数据库实例
    print('------')
    print('RDS ignore list:')
    RDS_ignoreList = []
    for alarm in CW_filteredIterator:
#       判断已有的监控告警是否为正准备创建的监控告警
        if alarm['MetricName'] == RDS_MetricName:
            for dimension in alarm["Dimensions"]:
                if dimension["Name"] == "DBInstanceIdentifier":
                    RDS_ignoreList.append(dimension["Value"])
                    print(dimension["Value"])


#   Drop CloudWatch alarm cascade: 
    print('------')
    for cw in RDS_ignoreList:
        if is_existed_inList(cw, RDS_nameList):
            print('Dropping CloudWatch alarm "RDS_'+RDS_MetricName+'" for: '+cw)
            CWalarms = CW_client.delete_alarms(
                AlarmNames=['RDS_'+RDS_MetricName+'-'+cw]
            )
            print('Dropped CloudWatch alarm "RDS_'+RDS_MetricName+'" for: '+cw)


#   Create customized CloudWatch alarms auto: 
    print ('')
    for rds_record in RDS_rawList:
#       预先定义SNS topic suffix，不同的CloudWatch告警通知会发送到不同的SNS topic
        rds_name = rds_record['DBInstanceArn'].split(':', 6)[6]
        print('------')
#       判断是否为MySQL数据库，且未创建对应的监控告警
        if is_existed_inList(rds_name, RDS_ignoreList) & (RDS_rawList[0]['Engine'] == 'mysql'):
            print('------')
            print('RDS name: '+rds_name)
            print('Creating CloudWatch alarm "RDS_'+RDS_MetricName+'" for: '+rds_name)
#           获取该RDS数据库对应的实例规格，查询map_maxConnections mapping所对应的max_connections
            for dict in RDS_rawList:
                if dict["DBInstanceIdentifier"] == rds_name:
                    max_connections = map_maxConnections(dict["DBInstanceClass"].split('.',2)[2])
                    print('max_connections = '+str(max_connections))
#           创建监控告警
            CWalarms = CW_client.put_metric_alarm(
                AlarmName='RDS_'+RDS_MetricName+'-'+rds_name, 
                AlarmDescription='Auto-created customized CloudWatch Alarm <RDS_'+RDS_MetricName+'>',
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
                MetricName=RDS_MetricName,
                Namespace="AWS/RDS",
                Statistic='Maximum',
                # 'SampleCount'|'Average'|'Sum'|'Minimum'|'Maximum'
#                ExtendedStatistic='p100',
                Dimensions=[
                    {
                        'Name': 'DBInstanceIdentifier',
                        'Value': rds_name
                    },
                ],
                Period=60,
#                Unit='Seconds',
                # 'Seconds'|'Microseconds'|'Milliseconds'|'Bytes'|'Kilobytes'|'Megabytes'|'Gigabytes'|'Terabytes'|'Bits'|'Kilobits'|'Megabits'|'Gigabits'|'Terabits'|'Percent'|'Count'|'Bytes/Second'|'Kilobytes/Second'|'Megabytes/Second'|'Gigabytes/Second'|'Terabytes/Second'|'Bits/Second'|'Kilobits/Second'|'Megabits/Second'|'Gigabits/Second'|'Terabits/Second'|'Count/Second'|'None'
                EvaluationPeriods=3,
                DatapointsToAlarm=2,
                Threshold=max_connections,
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
                        'Key': str('RDS_'+RDS_MetricName),
                        'Value': 'autocreated'
                    },
                ],
#                ThresholdMetricId='string'
            )

#           为该RDS数据库标记CWalarm-DatabaseConnections标签
            RDS_tags = RDS_client.add_tags_to_resource(
                ResourceName=rds_record['DBInstanceArn'],
                Tags=[
                    {
                        'Key': str('CWalarm-'+RDS_MetricName),
                        'Value': 'enabled'
                    },
                ]
            )
            print('Added tag "CWalarm-'+RDS_MetricName+'" to: '+rds_name)

            print('Created CloudWatch alarm "RDS_'+RDS_MetricName+'" for: '+rds_name)
            print()
        else: 
            print('No CloudWatch alarm created for: '+rds_name)
    return {
        'statusCode': 200,
        'body': json.dumps('Mission Complete!')
    }


#run_command('/var/task/aws --version')
#run_command('ls -l')
