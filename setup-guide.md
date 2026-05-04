python 3.12

docs/openapi.yaml파일을 참고하여 어떤 값이 필요한지, 어떤 데이터가 나오는지 파악하세요
아래의 링크에 들어가서 파일의 내용을 복사 붙여넣기 하면 됩니다
https://editor.swagger.io/





아래는 실행하지 마세요
```
 openapi-generator-cli generate `
>>   -i openapi.yaml `
>>   -g python `
>>   -o ./temp_stubs `
>>   --additional-properties=packageName=maple_api,projectName=maple_api
```