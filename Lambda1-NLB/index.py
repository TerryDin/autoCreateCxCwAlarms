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

NLB_MetricName = os.environ['MetricName']
MaxItems = os.environ['MaxItems']
SNS_topic_suffix = os.environ['SNS_topic_suffix']

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def is_existed_inList(target, list):
    if target in list:
        return False
    else:
        return True


#def run_command(command):
#    command_list = command.split(' ')
#
#    try:
#        logger.info("Running shell command: \"{}\"".format(command))
#        result = subprocess.run(command_list, stdout=subprocess.PIPE);
#        logger.info("Command output:\n---\n{}\n---".format(result.stdout.decode('UTF-8')))
#    except Exception as e:
#        logger.error("Exception: {}".format(e))
#        return False
#
#    return True


# The 'handler' Python function is the entry point for AWS Lambda function invocations.
def handler(event, context):

#    content = 'CloudWatch Alarm! {0}'.format(get_message(event))
#    webhook_uri = os.environ['CHIME_WEBHOOK']
#    requests.post(url=webhook_uri, json={ 'Content': content })
#    print('------')
#    print('print event')
#    print(event)


    stsClient = boto3.client('sts')
    accountId = stsClient.get_caller_identity().get('Account')
    print('------')
    print('Account: '+accountId)


#   List metrics through the pagination interface
    CW_client = boto3.client('cloudwatch')
    CW_paginator = CW_client.get_paginator('describe_alarms')
    CW_iterator = CW_paginator.paginate()
    CW_filteredIterator = CW_iterator.search("MetricAlarms[?MetricName==`"+NLB_MetricName+"` && Namespace==`AWS/NetworkELB`]")

        
#   Prepare target NLB list
    netELB_client = boto3.client('elbv2')
    netELB_paginator = netELB_client.get_paginator('describe_load_balancers')
    netELB_iterator = netELB_paginator.paginate(
        PaginationConfig={
            *# 最大创建NLB CloudWatch alarms的数量*
            *# 在产线实测阶段，可将值调整为2*
            *'MaxItems'**:** **MaxItems**,*
            # 演示分页，最大可以设置成400
            'PageSize': 20
        }
    )


#   Prepare NLB full list
    print('------')
    print('NLB full list:')
    netELB_rawList = []
    netELB_idList = []
    netELB_nameList = []
    for netELB_response in netELB_iterator:
#        'Scheme': 'internet-facing'
#        print(netELB_response['LoadBalancers'])
        netELB_rawList.extend(netELB_response['LoadBalancers'])
    for dict in netELB_rawList:
        for i in dict.items():
            if i[0] == "LoadBalancerArn":
                print(i[1].split('/',3)[2])
                netELB_idList.append(i[1].split('/',1)[1])
                netELB_nameList.append(i[1].split('/',3)[2])

#   Prepare NLB ignore list: 筛选出已经创建对应监控告警的NLB
    print('------')
    print('NLB ignore list:')
    netELB_ignoreList = []
    for alarm in CW_filteredIterator:
#       判断已有的监控告警是否为正准备创建的监控告警
        if alarm['MetricName'] == NLB_MetricName:
            for dimension in alarm["Dimensions"]:
                if dimension["Name"] == ["LoadBalancer"][0]:
                    netELB_ignoreList.append(dimension["Value"])
                    print(dimension["Value"].split('/',2)[1])


#   Drop CloudWatch alarm cascade:
    print('------')
    for cw in netELB_ignoreList:
        if is_existed_inList(cw, netELB_idList):
            print('Dropping CloudWatch alarm "netELB_'+NLB_MetricName+'" for: '+cw.split('/',2)[1])
            CWalarms = CW_client.delete_alarms(
                AlarmNames=['netELB_'+NLB_MetricName+'-'+cw.split('/',2)[1]]
            )
            print('Dropped CloudWatch alarm "netELB_'+NLB_MetricName+'" for: '+cw.split('/',2)[1])


#   Create customized CloudWatch alarms auto: 
    print ('')
    for netELB in netELB_rawList:
#       预先定义SNS topic suffix，不同的CloudWatch告警通知会发送到不同的SNS topic
        print('------')
#       判断是否为netELB，且未创建对应的监控告警
        if is_existed_inList(netELB["LoadBalancerArn"].split('/',1)[1], netELB_ignoreList) & (netELB["LoadBalancerArn"].split('/',1)[1].split('/',1)[0] == 'net'):
            print('------')
            print('NLB name: '+netELB['LoadBalancerName'])
            print('Creating CloudWatch alarm "netELB_'+NLB_MetricName+'" for: '+netELB['LoadBalancerName'])
            CWalarms = CW_client.put_metric_alarm(
                AlarmName='netELB_'+NLB_MetricName+'-'+netELB['LoadBalancerName'], 
                AlarmDescription='Auto-created customized CloudWatch Alarm <netELB_'+NLB_MetricName+'>',
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
                MetricName=NLB_MetricName,
                Namespace="AWS/NetworkELB",
                Statistic='Sum',
                # 'SampleCount'|'Average'|'Sum'|'Minimum'|'Maximum'
#                ExtendedStatistic='p100',
                Dimensions=[
                    {
                        'Name': 'LoadBalancer',
                        'Value': netELB['LoadBalancerArn'].split('/',1)[1]
                    },
                ],
                Period=60,
#                Unit='Seconds',
                # 'Seconds'|'Microseconds'|'Milliseconds'|'Bytes'|'Kilobytes'|'Megabytes'|'Gigabytes'|'Terabytes'|'Bits'|'Kilobits'|'Megabits'|'Gigabits'|'Terabits'|'Percent'|'Count'|'Bytes/Second'|'Kilobytes/Second'|'Megabytes/Second'|'Gigabytes/Second'|'Terabytes/Second'|'Bits/Second'|'Kilobits/Second'|'Megabits/Second'|'Gigabits/Second'|'Terabits/Second'|'Count/Second'|'None'
                EvaluationPeriods=3,
                DatapointsToAlarm=2,
                Threshold=1500000.0,
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
                        'Key': str('netELB_'+NLB_MetricName),
                        'Value': 'autocreated'
                    },
                ],
#                ThresholdMetricId='string'
            )

#           为该NLB标记CWalarm-ActiveFlowCount标签
            netELB_tags = netELB_client.add_tags(
                ResourceArns=[
                    netELB["LoadBalancerArn"]
                ],
                Tags=[
                    {
                        'Key': str('CWalarm-'+NLB_MetricName),
                        'Value': 'enabled'
                    },
                ]
            )
            print('Added tag "CWalarm-'+NLB_MetricName+'" to: '+netELB["LoadBalancerName"])

            print('Created CloudWatch alarm "netELB_'+NLB_MetricName+'" for: '+netELB["LoadBalancerName"])
            print()
        else: 
            print('No CloudWatch alarm created for: '+netELB["LoadBalancerName"])
    return {
        'statusCode': 200,
        'body': json.dumps('Mission Complete!')
    }

#run_command('/var/task/aws --version')
#run_command('ls -l')