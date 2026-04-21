import pandas as pd
from sqlalchemy import create_engine

# ==========================================
# 1. DB 접속 설정 
# ==========================================
DB_USER = 'root'        
DB_PASS = 'pass123#'        # ★마리아DB 비밀번호 꼭 본인 것으로 수정!
DB_HOST = 'localhost'   # ★3서버 자기 자신이므로 127.0.0.1 (로컬호스트)
DB_PORT = '3306'       # 우리가 변경한 포트
DB_NAME = 'camping_db'  # 아까 만든 DB 이름 (안 만드셨다면 아래 설명 참고)

# ==========================================
# 2. CSV 파일 읽기
# ==========================================
print("CSV 파일을 읽는 중...")
csv_file_path = '캠핑장_데이터_최종_마스터.csv' 
df = pd.read_csv(csv_file_path, encoding='utf-8-sig')

# ==========================================
# 3. 컬럼명 영어로 변경
# ==========================================
df = df.rename(columns={
    '번호': 'camspot_id', '야영장명': 'name', '주소': 'address',
    '화로대': 'fire_pit', '부대시설': 'facilities', '주변이용가능시설': 'surroundings',
    '테마환경': 'theme', '반려동물출입': 'pet_allowed',
    '비수기_평일_가격': 'price_off_weekday', '비수기_주말_가격': 'price_off_weekend',
    '성수기_평일_가격': 'price_peak_weekday', '성수기_주말_가격': 'price_peak_weekend',
    'naver_id': 'naver_id', 'states': 'states'
})

# ==========================================
# 4. DB 연결 및 통째로 밀어 넣기!
# ==========================================
print("MariaDB에 연결 중...")
engine_url = f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
engine = create_engine(engine_url)

print("데이터를 DB에 적재하는 중...")
df.to_sql(name='campsites', con=engine, if_exists='replace', index=False)
print("🎉 3서버에서 직접 캠핑장 데이터 MariaDB 적재 완벽 성공!!")