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

ES_MetricName = os.environ['MetricName']
MaxItems = os.environ['MaxItems']
SNS_topic_suffix = os.environ['SNS_topic_suffix']

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def is_existed_inList(target, list):
    if target in list:
        return False
    else:
        return True


#def map_maxConnections(instanceSize): 
#    if instanceSize == 'large':
#        return 1000
#    if instanceSize == 'xlarge':
#        return 2000
#    if instanceSize == '2xlarge':
#        return 3000
#    if instanceSize == '4xlarge':
#        return 5000
#    if instanceSize == '8xlarge':
#        return 10000
#    if instanceSize == '12xlarge':
#        return 15000
#    if instanceSize == '16xlarge':
#        return 20000
#    if instanceSize == '24xlarge':
#        return 30000
#    if instanceSize == 'small':
#        return 45
#    if instanceSize == 'medium':
#        return 90
#    else:
#        return 999


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
    CW_filteredIterator = CW_iterator.search("MetricAlarms[?MetricName==`"+ES_MetricName+"` && Namespace==`AWS/ES`]")
    
#   Prepare ElasticSearch nodes list
    print('------')
    print('ElasticSearch cluster & data nodes mapping: ')
    ES_nodesMapping = []
    CW_paginator_ESnodes = CW_client.get_paginator('list_metrics')
    CW_responseIterator_ESnodes = CW_paginator_ESnodes.paginate(
        Namespace='AWS/ES',
        # 直接可以从CloudWatch指标当中，获取ElasticSearch集群与Data nodes的mapping
        MetricName=ES_MetricName,
        PaginationConfig={
            'MaxItems': MaxItems
        }
    )
    CW_filteredIterator_ESnodes = CW_responseIterator_ESnodes
    for f in CW_filteredIterator_ESnodes:
        for metric in f['Metrics']:
            dimension = metric['Dimensions']
#           检验获取的是Domain(Cluster)与data nodes的mapping
            if (dimension[0]['Name'] == "DomainName") & (dimension[1]['Name'] == "NodeId"):
                ES_nodesMapping.append(dimension)
        print(ES_nodesMapping)


#   Prepare ElasticSearch domain names list
    print('------')
    print('Preparing ElasticSearch full list:')
#    ES_rawList = []
    ES_idList = []
    ES_nameList = []
    ES_client = boto3.client('es')
#   ElasticSearch集群的name list
    ES_domains = ES_client.list_domain_names()['DomainNames']
    for dict in ES_domains:
        i = dict['DomainName']
        ES_nameList.append(i)
        print('ElasticSearch cluster name: '+i)
#   ElasticSearch集群的ARN list
        ES_id = ES_client.describe_elasticsearch_domain(
            DomainName = i
        )
        ES_idList.append(ES_id['DomainStatus']['ARN'])
        print('- cluster ARN: '+str(ES_id['DomainStatus']['ARN']))
        print()


#   Prepare ElasticSearch ignore list: 筛选出已经创建对应监控告警的ElasticSearch集群
    print('------')
    print('ElasticSearch ignore list:')
    ES_ignoreList = []
    for alarm in CW_filteredIterator:
#       判断已有的监控告警是否为正准备创建的监控告警
        if alarm['MetricName'] == ES_MetricName:
            for dimension in alarm["Dimensions"]:
                if dimension["Name"] == "DomainName":
                    ES_ignoreList.append(dimension["Value"])
                    print(dimension["Value"])


#   Drop CloudWatch alarm cascade: 
    print('------')
    for cw in ES_ignoreList:
        if is_existed_inList(cw, ES_nameList):
            print('Dropping CloudWatch alarm "ES_'+ES_MetricName+'" for: '+cw)
            CWalarms = CW_client.delete_alarms(
                AlarmNames=['ES_'+ES_MetricName+'-'+cw]
            )
            print('Dropped CloudWatch alarm "ES_'+ES_MetricName+'" for: '+cw)


#   Create customized CloudWatch alarms auto: 
    print ('')
    for es_id in ES_idList:
#       预先定义SNS topic suffix，不同的CloudWatch告警通知会发送到不同的SNS topic
        es_name = es_id.split('/',2)[1]
        print('------')
#       判断是否并未创建对应的监控告警
        if is_existed_inList(es_name, ES_ignoreList):
            print('------')
#           mapping未创建对应监控的ElasticSearch cluster及其data nodes
            for node_record in ES_nodesMapping:
                if node_record[0]['Value'] == es_name:
                    node_id = node_record[1]['Value']
                    print('Target record found in ES_nodesMapping: '+str(node_record))
#                   创建Data nodes级别的监控
                    print('Creating CloudWatch alarm "ES_'+ES_MetricName+'" for Data node <'+node_id+'> of Cluster <'+es_name+'>')
#                   获取该ES集群节点对应的实例规格，查询map_maxConnections mapping所对应的max_connections
#                    for dict in ES_rawList:
#                    if dict["DBInstanceIdentifier"] == es_name:
#                        max_connections = map_maxConnections(dict["DBInstanceClass"].split('.',2)[2])
#                        print('max_connections = '+str(max_connections))
#                   创建监控告警
                    CWalarms = CW_client.put_metric_alarm(
                        AlarmName='ES_'+ES_MetricName+'-'+es_name+'_'+node_id,
                        AlarmDescription='Auto-created customized CloudWatch Alarm <ES_'+ES_MetricName+'>',
                        ActionsEnabled=True,
#                        OKActions=[
#                            'string',
#                        ],
                        AlarmActions=[
                            # 示例，发送到SNS
                            'arn:aws:sns:us-west-2:{}:customizedAlarmAction-{}'.format(accountId,SNS_topic_suffix)
                        ], 
#                        InsufficientDataActions=[
#                            'string',
#                        ],
                        MetricName=ES_MetricName,
                        Namespace="AWS/ES",
                        Statistic='Maximum',
                        # 'SampleCount'|'Average'|'Sum'|'Minimum'|'Maximum'
#                        ExtendedStatistic='p100',
#                        ElasticSearch支持cluster级别的监控:
#                        Dimensions = [
#                            {
#                                'Name': 'DomainName',
#                                'Value': es_name
#                            },{
#                                'Name': 'ClientId',
#                                'Value': accountId,
#                            }
#                        ],
#                       ElasticSearch支持data nodes级别的监控:
                        Dimensions = node_record,
#                        print(es_name['LoadBalancerArn'].split('/',1)[1])
                        Period=60,
#                        Unit='Seconds',
                        # 'Seconds'|'Microseconds'|'Milliseconds'|'Bytes'|'Kilobytes'|'Megabytes'|'Gigabytes'|'Terabytes'|'Bits'|'Kilobits'|'Megabits'|'Gigabits'|'Terabits'|'Percent'|'Count'|'Bytes/Second'|'Kilobytes/Second'|'Megabytes/Second'|'Gigabytes/Second'|'Terabytes/Second'|'Bits/Second'|'Kilobits/Second'|'Megabits/Second'|'Gigabits/Second'|'Terabits/Second'|'Count/Second'|'None'
                        EvaluationPeriods=60,
                        DatapointsToAlarm=2,
                        Threshold=75,
                        ComparisonOperator='GreaterThanOrEqualToThreshold',
                        # 'GreaterThanOrEqualToThreshold'|'GreaterThanThreshold'|'LessThanThreshold'|'LessThanOrEqualToThreshold'|'LessThanLowerOrGreaterThanUpperThreshold'|'LessThanLowerThreshold'|'GreaterThanUpperThreshold'
                        TreatMissingData='ignore',
#                        EvaluateLowSampleCountPercentile='ignore',
#                        Metrics=[
#                            {
#                                'Id': 'string',
#                                'MetricStat': {
#                                    'Metric': {
#                                        'Namespace': 'string',
#                                        'MetricName': 'string',
#                                        'Dimensions': [
#                                            {
#                                                'Name': 'string',
#                                                'Value': 'string'
#                                            },
#                                        ]
#                                    },
#                                    'Period': 123,
#                                    'Stat': 'string',
#                                    'Unit': 'Seconds'|'Microseconds'|'Milliseconds'|'Bytes'|'Kilobytes'|'Megabytes'|'Gigabytes'|'Terabytes'|'Bits'|'Kilobits'|'Megabits'|'Gigabits'|'Terabits'|'Percent'|'Count'|'Bytes/Second'|'Kilobytes/Second'|'Megabytes/Second'|'Gigabytes/Second'|'Terabytes/Second'|'Bits/Second'|'Kilobits/Second'|'Megabits/Second'|'Gigabits/Second'|'Terabits/Second'|'Count/Second'|'None'
#                                },
#                                'Expression': 'string',
#                                'Label': 'string',
#                                'ReturnData': True|False,
#                                'Period': 123
#                            },
#                        ],
                        Tags=[
                            {
                                'Key': str('ES_'+ES_MetricName),
                                'Value': 'autocreated'
                            },
                        ],
#                        ThresholdMetricId='string'
                    )

#                   为该ES集群标记CWalarm-JVMMemoryPressure标签
                    ES_tags = ES_client.add_tags(
                        ARN = es_id,
                        TagList = [
                            {
                                'Key': str('CWalarm-'+ES_MetricName),
                                'Value': 'enabled'
                            },
                        ]
                    )
                    print('Added tag "CWalarm-'+ES_MetricName+'" to: '+es_name)
                    
                    print('Created CloudWatch alarm "ES_'+ES_MetricName+'" for Data node <'+node_id+'> of Cluster <'+es_name+'>')
                    print()
        else: 
            print('No CloudWatch alarm created for: '+es_name)
    return {
        'statusCode': 200,
        'body': json.dumps('Mission Complete!')
    }


#run_command('/var/task/aws --version')
#run_command('ls -l')