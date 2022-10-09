AWS_PAGER="" aws dynamodb create-table --cli-input-json file://captions.json --endpoint-url=http://34.93.83.118:4566
AWS_PAGER="" aws dynamodb create-table --cli-input-json file://users.json --endpoint-url=http://34.93.83.118:4566
aws s3 mb s3://mybucket --endpoint-url=http://34.93.83.118:4566