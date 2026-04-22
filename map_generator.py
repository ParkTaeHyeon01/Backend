import os
import json
import folium
import pandas as pd
from folium.plugins import MarkerCluster
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# --- DB 설정 (제공해주신 정보 적용) ---
DB_USER, DB_PASS, DB_HOST, DB_PORT, DB_NAME = 'root', 'pass123#', '127.0.0.1', '3306', 'camping_db'
MARIA_URL = f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
engine = create_engine(MARIA_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def generate_static_maps():
    db = SessionLocal()
    # 저장될 폴더 생성
    os.makedirs("static/maps", exist_ok=True)
    
    try:
        print("데이터 조회 중...")
        # 1. 전체 캠핑장 데이터 조회 (클러스터 및 마커용)
        query_sites = text("SELECT name, address, lat, lng FROM campsites WHERE lat IS NOT NULL")
        sites = db.execute(query_sites).mappings().all()
        
        # 2. 지역별 밀도 데이터 조회
        query_count = text("""
            SELECT 
                CASE 
                    WHEN address LIKE '서울%' THEN 'Seoul'
                    WHEN address LIKE '제주%' THEN 'Jeju'
                    WHEN address LIKE '경기%' THEN 'Gyeonggi-do'
                    WHEN address LIKE '강원%' THEN 'Gangwon-do'
                    WHEN address LIKE '인천%' THEN 'Incheon'
                    WHEN address LIKE '부산%' THEN 'Busan'
                    WHEN address LIKE '대구%' THEN 'Daegu'
                    WHEN address LIKE '대전%' THEN 'Daejeon'
                    WHEN address LIKE '광주%' THEN 'Gwangju'
                    WHEN address LIKE '울산%' THEN 'Ulsan'
                    WHEN address LIKE '세종%' THEN 'Sejong'
                    WHEN address LIKE '충북%' OR address LIKE '충청북도%' THEN 'Chungcheongbuk-do'
                    WHEN address LIKE '충남%' OR address LIKE '충청남도%' THEN 'Chungcheongnam-do'
                    WHEN address LIKE '전북%' OR address LIKE '전라북도%' THEN 'Jeollabuk-do'
                    WHEN address LIKE '전남%' OR address LIKE '전라남도%' THEN 'Jeollanam-do'
                    WHEN address LIKE '경북%' OR address LIKE '경상북도%' THEN 'Gyeongsangbuk-do'
                    WHEN address LIKE '경남%' OR address LIKE '경상남도%' THEN 'Gyeongsangnam-do'
                    ELSE 'Other'
                END as province_name,
                COUNT(*) as camp_count
            FROM campsites
            WHERE address IS NOT NULL
            GROUP BY province_name
        """)
        counts = db.execute(query_count).mappings().all()
        df = pd.DataFrame(counts)

        # --- [1] 밀도 지도(Density Map) 생성 섹션 수정 ---
        print("밀도 지도 생성 중 (마커 포함)...")
        m_density = folium.Map(location=[36.5, 127.5], zoom_start=7, tiles="OpenStreetMap")

        # 1. 지역 경계 밀도 색상 입히기 (Choropleth)
        folium.Choropleth(
            geo_data='skorea-provinces-geo.json',
            data=df,
            columns=['province_name', 'camp_count'],
            key_on='feature.properties.NAME_1',
            fill_color='YlOrRd',
            fill_opacity=0.4, # 마커가 잘 보이도록 배경 투명도 조절
            line_opacity=0.5,
            legend_name='지역별 캠핑장 수'
        ).add_to(m_density)

        # 2. 밀도 지도 위에 개별 캠핑장 점(CircleMarker) 추가
        for site in sites:
            folium.CircleMarker(
                location=[float(site['lat']), float(site['lng'])],
                radius=4,               # 점 크기
                color='white',          # 테두리
                weight=0.5,
                fill=True,
                fill_color='#d63031',   # 진한 빨간색
                fill_opacity=0.8,
                popup=folium.Popup(f'<b>{site["name"]}</b><br>{site["address"]}', max_width=200),
                tooltip=site['name']
            ).add_to(m_density)

        # 파일 저장
        m_density.save("static/maps/density.html")
        print("마커가 포함된 밀도 지도가 저장되었습니다.")

        # --- [2] 클러스터 지도(Cluster Map) 생성 ---
        print("클러스터 지도 생성 중...")
        m_cluster = folium.Map(location=[36.5, 127.5], zoom_start=7, tiles="OpenStreetMap")
        marker_cluster = MarkerCluster().add_to(m_cluster)

        for site in sites:
            folium.CircleMarker(
                location=[float(site['lat']), float(site['lng'])],
                radius=5,
                color='white',
                weight=1,
                fill=True,
                fill_color='#d63031',
                fill_opacity=0.9,
                popup=folium.Popup(f'<b>{site["name"]}</b><br>{site["address"]}', max_width=250),
                tooltip=site['name']
            ).add_to(marker_cluster)

        m_cluster.save("static/maps/cluster.html")
        print("모든 지도가 static/maps/ 폴더에 저장되었습니다.")

    except Exception as e:
        print(f"오류 발생: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    generate_static_maps()