import mysql.connector
import requests
import time

# --- [설정 영역] ---
KAKAO_API_KEY = "d0191abcbf3a0148672a60a17dc7b7f7"
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'pass123#', # MariaDB 비밀번호 입력
    'database': 'camping_db'
}

def get_coords(address):
    """카카오 API를 통해 주소를 위경도로 변환 (y: 위도, x: 경도)"""
    url = f"https://dapi.kakao.com/v2/local/search/address.json?query={address}"
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            result = response.json()
            if result['documents']:
                # 카카오 API: y=위도(lat), x=경도(lng)
                return float(result['documents'][0]['y']), float(result['documents'][0]['x'])
    except Exception as e:
        print(f"  - API 에러: {e}")
    return None, None

def main():
    try:
        # 1. DB 연결
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)
        print("✅ MariaDB 연결 성공")

        # 2. lat, lng 컬럼이 없는 경우 자동 추가
        try:
            print("🔍 테이블 구조 확인 및 컬럼 추가 시도...")
            cursor.execute("ALTER TABLE campsites ADD COLUMN lat DECIMAL(10, 7) NULL AFTER address")
            cursor.execute("ALTER TABLE campsites ADD COLUMN lng DECIMAL(11, 7) NULL AFTER lat")
            conn.commit()
            print("  - lat, lng 컬럼을 새로 생성했습니다.")
        except mysql.connector.Error as err:
            if err.errno == 1060: # 이미 컬럼이 존재하는 경우
                print("  - lat, lng 컬럼이 이미 존재합니다. 변환 작업을 계속합니다.")
            else:
                print(f"  - 컬럼 확인 중 알 수 없는 오류: {err}")

        # 3. 변환 대상 조회 (주소는 있고 좌표는 없는 데이터)
        cursor.execute("SELECT camspot_id, address, name FROM campsites WHERE address IS NOT NULL AND lat IS NULL")
        targets = cursor.fetchall()
        
        total = len(targets)
        print(f"🚀 총 {total}건의 데이터 변환을 시작합니다.")

        if total == 0:
            print("이미 모든 데이터에 좌표가 입력되어 있습니다.")
            return

        # 4. 반복 변환 및 업데이트
        success_count = 0
        for i, row in enumerate(targets):
            addr = row['address']
            
            # 주소 데이터 전처리 (불필요한 상세 정보 제외)
            if not addr or addr in ["정보없음", "null"]:
                continue
            
            lat, lng = get_coords(addr)
            
            if lat and lng:
                update_sql = "UPDATE campsites SET lat = %s, lng = %s WHERE camspot_id = %s"
                cursor.execute(update_sql, (lat, lng, row['camspot_id']))
                conn.commit()
                success_count += 1
                print(f"[{i+1}/{total}] 성공: {row['name']} -> ({lat}, {lng})")
            else:
                print(f"[{i+1}/{total}] 실패: {row['name']} (주소 검색 불가: {addr})")
            
            # API 제한 방지 (카카오 로컬 API 권장 속도 준수)
            time.sleep(0.05)

        print("\n✨ 작업 완료!")
        print(f"성공: {success_count} / 전체: {total}")

    except mysql.connector.Error as err:
        print(f"❌ DB 오류 발생: {err}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()
            print("🔌 DB 연결 종료")

if __name__ == "__main__":
    main()