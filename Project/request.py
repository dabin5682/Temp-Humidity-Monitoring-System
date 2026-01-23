import requests

# ================= 사용자 입력 부분 =================
rest_api_key = '4e60aa05456a9b9f92c926e117f37379'
authorize_code = 'duq_VHdJd3Xt1oYXO4rlyeKWztKpYFrB5x4RzEW7KLvupWcGVxJkngAAAAQKFxKWAAABms-BFYDgLMgnBn6ZSw'

# 등록된 주소와 완벽히 일치해야 함 (수정 금지)
redirect_uri = 'http://localhost:5000/oauth' 
# =================================================

url = 'https://kauth.kakao.com/oauth/token'
data = {
    'grant_type': 'authorization_code',
    'client_id': rest_api_key,
    'redirect_uri': redirect_uri,
    'code': authorize_code,
}

response = requests.post(url, data=data)
tokens = response.json()

print("="*30)
if "access_token" in tokens:
    print("성공! 아래 내용을 복사해서 kakao_token.json 파일을 만드세요.\n")
    print("{")
    print(f'    "access_token": "{tokens["access_token"]}",')
    print(f'    "refresh_token": "{tokens["refresh_token"]}"')
    print("}")
else:
    print("실패했습니다. 에러 메시지:")
    print(tokens)
print("="*30)