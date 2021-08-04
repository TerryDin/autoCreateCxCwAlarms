Set-DefaultAWSRegion -Region us-west-2
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
  Description = 'Customize CloudWatch alarms notification for RDS - DatabaseConnections RDS_DatabaseConnections. '
  ZipFilename = $ZipFileName
  Handler = 'index.lambda_handler'
  Role = 'arn:aws:iam::532134256174:role/lambdaExecRole-autoCreateCxCwAlarms_RDS'
  Environment_Variable = @{
    NotificationSNSTopic = 'arn:aws:sns:us-west-2:532134256174:To-DBA_team'
    TimeZoneCode = 'Asia/Hong_Kong'
    TimezoneInitial = 'UTC+8'
  # CHIME_WEBHOOK = 'https://hooks.chime.aws/incomingwebhooks/3c8fd66f-6e40-4375-9fe8-0ba6a57cb375?token=aWVuczdtTUd8MXxCZC05SmNIZ3RqUFMydXpydllNTUx2em15WU5YZVNrX0ZodWc3THljdFg0'
  }
  MemorySize = 512
  Timeout = 60
  Layer = "arn:aws:lambda:us-west-2:532134256174:layer:customizedAlarms-RDS_DatabaseConnections:1"
}

Remove-LMFunction -FunctionName $Function.FunctionName -Force
Publish-LMFunction @Function


Write-Host -Object 'Deployment completed' -ForegroundColor Green