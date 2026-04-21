import matplotlib
matplotlib.use('Agg') # 서버 환경용 백엔드 설정
import matplotlib.pyplot as plt
import pandas as pd
from sqlalchemy import create_engine, text
import asyncio
import os

# 폰트 및 저장 경로 설정
os.makedirs('static/images', exist_ok=True)
plt.rc('font', family='Malgun Gothic')
plt.rc('axes', unicode_minus=False)

# MariaDB 연결 정보
MARIA_URL = "mysql+pymysql://root:pass123#@127.0.0.1:3306/camping_db?charset=utf8mb4"

async def generate_separate_stats_images():
    # 1. 데이터 가져오기 (MariaDB)
    engine = create_engine(MARIA_URL)
    try:
        with engine.connect() as conn:
            query = text("SELECT address FROM campsites")
            df = pd.read_sql(query, conn)
    except Exception as e:
        print(f"❌ DB 연결 오류: {e}")
        return

    # 데이터 가공: 주소에서 지역명(도/시) 추출
    df['region'] = df['address'].apply(lambda x: x.split()[0] if x else '미분류')
    region_counts = df['region'].value_counts().head(10)

    # --- [그래프 1: 지역별 캠핑장 분포 (Bar Chart)] ---
    plt.figure(figsize=(10, 6))
    colors = plt.cm.get_cmap('Paired')(range(len(region_counts)))
    
    plt.bar(region_counts.index, region_counts.values, color=colors)
    plt.title("전국 지역별 캠핑장 분포 (TOP 10)", fontsize=16, fontweight='bold', pad=20)
    plt.ylabel("캠핑장 수 (개)", fontsize=12)
    plt.xticks(rotation=45)
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.tight_layout()
    
    plt.savefig('static/images/region_bar.png', dpi=150)
    plt.close()
    print("✅ 지역별 바 차트 저장 완료: static/images/region_bar.png")

    # --- [그래프 2: 주요 지역별 점유율 (Donut Chart)] ---
    plt.figure(figsize=(8, 8))
    
    # 도넛 차트 생성
    plt.pie(
        region_counts, 
        labels=region_counts.index, 
        autopct='%1.1f%%', 
        startangle=140, 
        colors=colors,
        pctdistance=0.85,
        wedgeprops={'width': 0.5, 'edgecolor': 'w'} # 도넛 형태 설정
    )
    
    # 중앙 텍스트 추가
    plt.text(0, 0, f'전국 주요\n지역 비중', ha='center', va='center', 
             fontsize=14, fontweight='bold')
    
    plt.title("주요 지역별 캠핑장 점유율", fontsize=16, fontweight='bold', pad=20)
    plt.tight_layout()
    
    plt.savefig('static/images/region_donut.png', dpi=150)
    plt.close()
    print("✅ 지역별 도넛 차트 저장 완료: static/images/region_donut.png")

if __name__ == "__main__":
    asyncio.run(generate_separate_stats_images())