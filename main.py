from fastapi.staticfiles import StaticFiles
import matplotlib
# [중요] GUI가 없는 서버 환경을 위해 백엔드를 'Agg'로 고정 (Tkinter 충돌 방지)
matplotlib.use('Agg') 
import matplotlib.pyplot as plt
from fastapi import FastAPI, HTTPException, Path, Query, status
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from typing import Optional, List
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from motor.motor_asyncio import AsyncIOMotorClient
from konlpy.tag import Okt
from collections import Counter
from wordcloud import WordCloud
import os
import io
import re
import joblib
import pandas as pd
from PIL import Image
import numpy as np
from fastapi.middleware.cors import CORSMiddleware


# --- [환경 및 폰트 설정] ---
# KoNLPy를 위한 Java 경로 설정
os.environ['JAVA_HOME'] = r'C:\Program Files\Java\jdk-17.0.18' 
plt.rc('font', family='Malgun Gothic') 
plt.rc('axes', unicode_minus=False) 
FONT_PATH = 'C:/Windows/Fonts/malgun.ttf' 

app = FastAPI(title="Camping Info & Sentiment API")

# 프론트엔드 주소 허용 설정
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,            # 특정 도메인 허용
    allow_credentials=True,
    allow_methods=["*"],              # 모든 HTTP 메서드(GET, POST 등) 허용
    allow_headers=["*"],              # 모든 HTTP 헤더 허용
)

# --- 1. 데이터베이스 및 분석 엔진 로드 ---

# [MariaDB]
DB_USER, DB_PASS, DB_HOST, DB_PORT, DB_NAME = 'root', 'pass123#', '127.0.0.1', '3306', 'camping_db'
MARIA_URL = f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
engine = create_engine(MARIA_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# [MongoDB]
MONGO_URL = "mongodb://localhost:27017"
mongo_client = AsyncIOMotorClient(MONGO_URL)
mongo_db = mongo_client.crawling_db
review_collection = mongo_db.camp_reviews

# [Sentiment Analysis Model]
print("-> 모델 및 분석 엔진 로드 중...")
model = joblib.load('camp_sentiment_model.pkl')
tfidf = joblib.load('camp_tfidf_vectorizer.pkl')
# Okt 객체를 전역 선언하여 JVM 중복 생성 및 충돌 방지
okt = Okt() 
tfidf.tokenizer = okt.morphs

STOPWORDS = [
    '있다', '없다', '좋다', '같다', '이다', '아니다', '그냥', '진짜', '너무', 
    '정말', '매우', '아주', '조금', '많다', '적다', '하나', '번', '들다', 
    '하다', '되다', '보고', '가다', '오다', '여기', '저기', '생각', '느낌',
    '때문', '정도', '다시', '항상', '보통', '전체', '부분', '이것', '그것',
    '다음', '보기', '자주', '사용', '통해', '가지', '경우', '내용', '확인',
    '그렇다', '이용', '내용', '진짜', '정말', '생각', '우리', '하나', '캠핑',
    '캠핑장', '예약', '방문', '정도', '때문', '다시', '사이트'
]

# --- 2. 데이터 모델 ---

class CampgroundResponse(BaseModel):
    camspot_id: int
    name: str
    address: str
    fire_pit: Optional[str]
    facilities: Optional[str]
    surroundings: Optional[str]
    theme: Optional[str]
    pet_allowed: Optional[str]
    price_off_weekday: Optional[int]
    price_off_weekend: Optional[int]
    price_peak_weekday: Optional[int]
    price_peak_weekend: Optional[int]
    naver_id: Optional[str]
    states: Optional[str]

    class Config:
        from_attributes = True

# --- 3. API 엔드포인트 ---

@app.get("/health", tags=["System"])
async def health_check():
    try:
        await mongo_client.admin.command('ping')
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "healthy"}
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "unhealthy", "error": str(e)})

# [1] 캠핑장 목록 조회
@app.get("/campgrounds", response_model=List[CampgroundResponse], tags=["Campgrounds"])
async def get_campgrounds(page: int = Query(1, ge=1)):
    db = SessionLocal()
    per_page = 50
    offset = (page - 1) * per_page
    try:
        query = text("SELECT * FROM campsites LIMIT :limit OFFSET :offset")
        result = db.execute(query, {"limit": per_page, "offset": offset})
        return [dict(row._mapping) for row in result]
    finally:
        db.close()

# [2] 캠핑장 상세 조회
@app.get("/campgrounds/{id}", response_model=CampgroundResponse, tags=["Campgrounds"])
async def get_campground_detail(id: int = Path(...)):
    db = SessionLocal()
    try:
        query = text("SELECT * FROM campsites WHERE camspot_id = :id")
        result = db.execute(query, {"id": id}).mappings().first()
        if not result:
            raise HTTPException(status_code=404, detail="Campground not found")
        return dict(result)
    finally:
        db.close()

# [5-1] 긍정 키워드 워드클라우드
@app.get("/campgrounds/{id}/dashboard/positive", tags=["Visualization"])
async def get_positive_wordcloud(id: int):
    return await generate_sentiment_wordcloud(id, target_sentiment=1)

# [5-2] 부정 키워드 워드클라우드
@app.get("/campgrounds/{id}/dashboard/negative", tags=["Visualization"])
async def get_negative_wordcloud(id: int):
    return await generate_sentiment_wordcloud(id, target_sentiment=0)

# [6] 시기별 방문 리뷰 갯수 (가독성 개선 및 폰트 크기 확대 버전)
@app.get("/campgrounds/{id}/line", tags=["Visualization"])
async def get_campground_visit_trend(id: int):
    db = SessionLocal()
    try:
        # 1. MariaDB에서 캠핑장 이름 조회
        camp_info = db.execute(text("SELECT name FROM campsites WHERE camspot_id = :id"), {"id": id}).mappings().first()
        camp_name = camp_info['name'] if camp_info else f"캠핑장 {id}"
        
        # 2. MongoDB에서 리뷰 데이터 조회
        doc = await review_collection.find_one({"camp_id": str(id)})
        if not doc or not doc.get("reviews"):
            raise HTTPException(status_code=404, detail="방문 추이 데이터가 없습니다.")

        # 3. 날짜 파싱 및 데이터프레임 생성
        dates = []
        for r in doc['reviews']:
            match = re.search(r'(\d{4})년\s+(\d{1,2})월', r['date'])
            if match:
                year, month = match.groups()
                dates.append(f"{year}-{int(month):02d}")

        if not dates:
             raise HTTPException(status_code=404, detail="유효한 날짜 데이터가 없습니다.")

        df = pd.DataFrame(dates, columns=['month'])
        trend = df['month'].value_counts().sort_index()

        # 4. 그래프 생성
        plt.clf()  # 이전 그림 삭제
        # 부모 프레임에 꽉 차도록 사이즈 조정 (가로: 14, 세로: 7)
        plt.figure(figsize=(14, 7))
        
        # 그래프 선 스타일 개선
        plt.plot(trend.index, trend.values, marker='o', color='#E53935', 
                 linewidth=4, markersize=10, markerfacecolor='white', markeredgewidth=2)
        
        # 타이틀 및 라벨 설정 (폰트 사이즈 16)
        plt.xlabel("방문 시기 (연-월)", fontsize=16, labelpad=15)
        plt.ylabel("리뷰 수 (건)", fontsize=16, labelpad=15)

        # --- [가독성 개선: 눈금 및 라벨 폰트 크기 16] ---
        # X축 눈금 설정
        interval = max(1, len(trend) // 10) # 데이터 양에 따라 자동으로 간격 조절
        plt.xticks(ticks=range(0, len(trend), interval), 
                   labels=trend.index[::interval], 
                   rotation=45, 
                   fontsize=16) # X축 텍스트 크기 16
        
        # Y축 눈금 설정
        plt.yticks(fontsize=16) # Y축 텍스트 크기 16

        # 배경 그리드 설정
        plt.grid(True, axis='y', linestyle='--', alpha=0.7)
        plt.gca().spines['top'].set_visible(False)
        plt.gca().spines['right'].set_visible(False)
        
        # 레이아웃 여백 최소화 (프레임에 맞게 동적 변동 지원)
        plt.tight_layout()

        # 5. 이미지 스트림 생성 및 반환
        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=120) # 선명도 상향
        buf.seek(0)
        plt.close()
        
        return StreamingResponse(buf, media_type="image/png")
        
    except Exception as e:
        print(f"Graph Error: {e}")
        raise HTTPException(status_code=500, detail="그래프 생성 중 오류가 발생했습니다.")
    finally:
        db.close()

# [7] 시기별 방문 비중 분석 (파이 차트)
@app.get("/campgrounds/{id}/pie", tags=["Visualization"])
async def get_campground_visit_donut(id: int):
    db = SessionLocal()
    try:
        # 1. MariaDB에서 캠핑장 이름 조회
        camp_info = db.execute(text("SELECT name FROM campsites WHERE camspot_id = :id"), {"id": id}).mappings().first()
        camp_name = camp_info['name'] if camp_info else f"캠핑장 {id}"
        
        # 2. MongoDB에서 리뷰 데이터 조회
        doc = await review_collection.find_one({"camp_id": str(id)})
        if not doc or not doc.get("reviews"):
            raise HTTPException(status_code=404, detail="방문 데이터가 없습니다.")

        # 3. 데이터 가공 (연도 추출)
        years = []
        for r in doc['reviews']:
            match = re.search(r'(\d{4})년', r['date'])
            if match:
                years.append(f"{match.group(1)}년")

        if not years:
             raise HTTPException(status_code=404, detail="유효한 날짜 데이터가 없습니다.")

        df = pd.DataFrame(years, columns=['year'])
        data = df['year'].value_counts().sort_index()
        total_reviews = sum(data.values)

        # 4. 도넛 차트 생성
        plt.clf()
        plt.figure(figsize=(10, 8))
        
        # 파이 차트 그리기 (wedgeprops로 중앙을 비움)
        wedges, texts, autotexts = plt.pie(
            data, 
            labels=data.index, 
            autopct='%1.1f%%', 
            startangle=140, 
            colors=plt.cm.Set3.colors,
            pctdistance=0.85, # 퍼센트 글자 위치 조절
            wedgeprops={'width': 0.6, 'edgecolor': 'w'} # 도넛 두께 및 경계선 설정
        )

        # 중앙에 총 리뷰 수 텍스트 추가
        plt.text(0, 0, f'총 리뷰\n{total_reviews}건', ha='center', va='center', 
                 fontsize=15, fontweight='bold', color='#333333')

        # 글꼴 스타일 설정
        plt.setp(texts, size=12, fontweight='bold')
        plt.setp(autotexts, size=11, color='black')
        
        # 범례 추가
        plt.legend(data.index, title="방문 연도", loc="center left", bbox_to_anchor=(1, 0, 0.5, 1))
        
        plt.tight_layout()

        # 5. 이미지 반환
        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=100, bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        return StreamingResponse(buf, media_type="image/png")
        
    except Exception as e:
        print(f"Donut Chart Error: {e}")
        raise HTTPException(status_code=500, detail="차트 생성 중 오류가 발생했습니다.")
    finally:
        db.close()

# [8-1] 메인페이지: 지역별 분포 바 차트 즉시 반환
@app.get("/main/stats/region-bar", tags=["Visualization"])
async def get_main_region_bar():
    image_path = "static/images/region_bar.png"
    if not os.path.exists(image_path):
        raise HTTPException(status_code=404, detail="지역별 분포 이미지가 생성되지 않았습니다.")
    
    return FileResponse(image_path, media_type="image/png")

# [8-2] 메인페이지: 지역별 비중 도넛 차트 즉시 반환
@app.get("/main/stats/region-pie", tags=["Visualization"])
async def get_main_region_donut():
    image_path = "static/images/region_donut.png"
    if not os.path.exists(image_path):
        raise HTTPException(status_code=404, detail="지역별 비중 이미지가 생성되지 않았습니다.")
    
    return FileResponse(image_path, media_type="image/png")

# [8-3] 메인페이지: 지역별 감성 지수 차트 즉시 반환
@app.get("/main/stats/region-sentiment", tags=["Visualization"])
async def get_main_region_sentiment():
    image_path = "static/images/region_sentiment.png"
    if not os.path.exists(image_path):
        raise HTTPException(status_code=404, detail="지역별 감성 지수 이미지가 생성되지 않았습니다.")
    
    return FileResponse(image_path, media_type="image/png")


# --- [추가된 대시보드 전용 데이터 모델] ---
class DashboardSummary(BaseModel):
    total_count: int
    avg_price: int
    total_reviews: int

# --- [추가된 대시보드 관련 API 엔드포인트] ---

# 1. 대시보드 상단 KPI 카드 (총 캠핑장 수, 평균 가격, 총 방문 수)
@app.get("/main/stats/summary", response_model=DashboardSummary, tags=["Dashboard"])
async def get_dashboard_summary():
    db = SessionLocal()
    try:
        # MariaDB: 캠핑장 총 개수 및 평균 가격 집계
        query = text("SELECT COUNT(*) as cnt, AVG(price_off_weekday) as avg_p FROM campsites")
        result = db.execute(query).mappings().first()
        
        # MongoDB: 전체 리뷰(방문) 수 집계
        pipeline = [
            {"$project": {"count": {"$size": "$reviews"}}},
            {"$group": {"_id": None, "total": {"$sum": "$count"}}}
        ]
        mongo_result = await review_collection.aggregate(pipeline).to_list(1)
        total_visits = mongo_result[0]['total'] if mongo_result else 0

        return {
            "total_count": result['cnt'] or 0,
            "avg_price": int(result['avg_p'] or 0),
            "total_reviews": total_visits
        }
    finally:
        db.close()

# 2. 하단 왼쪽: 지역별 현황 (지역별 캠핑장 수 및 평균 가격)
@app.get("/main/stats/regions", tags=["Dashboard"])
async def get_region_stats():
    db = SessionLocal()
    try:
        # 주소 앞 2글자를 기준으로 그룹화하여 통계 산출
        query = text("""
            SELECT 
                region, COUNT(*) as count, AVG(price_off_weekday) as avg_price
            FROM (
                SELECT 
                    CASE 
                        WHEN address LIKE '경기%' THEN '경기'
                        WHEN address LIKE '서울%' THEN '서울'
                        WHEN address LIKE '강원%' THEN '강원'
                        WHEN address LIKE '충남%' OR address LIKE '충청남도%' THEN '충남'
                        WHEN address LIKE '충북%' OR address LIKE '충청북도%' THEN '충북'
                        WHEN address LIKE '경남%' OR address LIKE '경상남도%' THEN '경남'
                        WHEN address LIKE '경북%' OR address LIKE '경상북도%' THEN '경북'
                        WHEN address LIKE '전남%' OR address LIKE '전라남도%' THEN '전남'
                        WHEN address LIKE '전북%' OR address LIKE '전라북도%' THEN '전북'
                        WHEN address LIKE '제주%' THEN '제주'
                        ELSE '기타'
                    END as region,
                    price_off_weekday
                FROM campsites
                WHERE address IS NOT NULL AND address != '' AND address NOT LIKE '정보%'
            ) t
            WHERE region != '기타'
            GROUP BY region
            ORDER BY count DESC
        """)
        results = db.execute(query).mappings().all()
        return [dict(r) for r in results]
    finally:
        db.close()

# 3. 중앙: 전체 캠핑장 시기별 방문량 선그래프 (실시간 생성)
@app.get("/main/stats/visit-trend", tags=["Dashboard"])
async def get_main_visit_trend():
    try:
        # MongoDB의 모든 리뷰 날짜를 가져와서 월별 집계
        cursor = review_collection.find({}, {"reviews.date": 1})
        all_dates = []
        async for doc in cursor:
            if "reviews" in doc:
                for r in doc["reviews"]:
                    match = re.search(r'(\d{4})년\s+(\d{1,2})월', r['date'])
                    if match:
                        all_dates.append(f"{match.group(1)}-{int(match.group(2)):02d}")

        if not all_dates:
            raise HTTPException(status_code=404, detail="데이터가 없습니다.")

        df = pd.DataFrame(all_dates, columns=['month'])
        trend = df['month'].value_counts().sort_index()

        # 그래프 초기화
        plt.clf()
        fig, ax = plt.subplots(figsize=(14, 6)) # 가로 길이를 조금 더 늘림
        
        # 선 그래프 스타일 (대시보드 테마색 적용)
        ax.plot(trend.index, trend.values, marker='o', color='#0D9488', 
                 linewidth=3, markersize=8, markerfacecolor='white', markeredgewidth=2)
        ax.fill_between(trend.index, trend.values, color='#0D9488', alpha=0.1)

        # --- [가독성 개선 핵심 포인트] ---
        # 1. 데이터가 많을 경우 눈금을 일정 간격으로 건너뜀 (예: 3개월 단위)
        interval = max(1, len(trend) // 10) # 전체 데이터 길이에 맞춰 동적 간격 계산
        plt.xticks(ticks=range(0, len(trend), interval), 
                   labels=trend.index[::interval], 
                   rotation=45, 
                   fontsize=20) # 글자 크기 확대
        
        plt.yticks(fontsize=18) # Y축 글자 크기 확대
        
        # 2. 불필요한 테두리 제거 및 그리드 설정
        ax.grid(True, axis='y', linestyle='--', alpha=0.3)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        
        # 3. 여백 최적화
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=150) # 해상도 유지
        buf.seek(0)
        plt.close()
        return StreamingResponse(buf, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def generate_sentiment_wordcloud(camp_id: int, target_sentiment: int):
    doc = await review_collection.find_one({"camp_id": str(camp_id)})
    if not doc or not doc.get('reviews'):
        raise HTTPException(status_code=404, detail="리뷰 데이터를 찾을 수 없습니다.")

    words_list = []
    for rev in doc['reviews']:
        content = rev.get('content', '')
        if not content: continue
        
        # 감정 예측 (1: 긍정, 0: 부정)
        pred = model.predict(tfidf.transform([content]))[0]
        
        if pred == target_sentiment:
            tokens = okt.pos(content, stem=True)
            words = [w for w, t in tokens if t in ['Noun', 'Adjective'] 
                     and len(w) > 1 and w not in STOPWORDS]
            words_list.extend(words)

    # --- [개선 포인트: 빈도수 필터링] ---
    word_counts = Counter(words_list)
    
    # 1. 너무 적게 등장한 단어 제외 (예: 최소 2회 이상 등장한 단어만 유지)
    # 데이터 양에 따라 'count >= 2' 숫자를 조절하세요.
    filtered_counts = {word: count for word, count in word_counts.items() if count >= 2}

    if not filtered_counts:
        raise HTTPException(status_code=404, detail="분석 결과 해당 감정의 핵심 키워드가 부족합니다.")

    # 그래프 생성 및 초기화
    plt.clf()
    colormap = 'summer' if target_sentiment == 1 else 'autumn'
    title_text = "긍정 키워드 분석" if target_sentiment == 1 else "부정 키워드 분석"
    
    # [주의] campimg.png 파일이 프로젝트 루트 경로에 있어야 합니다.
    try:
        img = np.array(Image.open('campimg.png'))
    except Exception:
        img = None # 이미지 파일이 없을 경우 대비
    
    # --- [개선 포인트: WordCloud 설정 변경] ---
    wc = WordCloud(
        font_path=FONT_PATH,
        background_color='white',
        width=800,
        height=400,
        colormap=colormap,
        mask=img,
        max_words=40,           # [추가] 화면에 표시할 최대 단어 수를 40개로 제한
        min_font_size=15,       # [추가] 너무 작은 글자가 생기지 않도록 최소 폰트 크기 지정
        max_font_size=100,      # [추가] 특정 단어가 너무 커지는 것 방지
        prefer_horizontal=0.9   # [추가] 가로 글씨 위주로 배치하여 가독성 향상
    ).generate_from_frequencies(filtered_counts)
    
    plt.figure(figsize=(10, 5))
    plt.imshow(wc, interpolation='bilinear')
    plt.axis('off')
    
    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches='tight')
    buf.seek(0)
    plt.close() # 자원 해제 필수
    
    return StreamingResponse(buf, media_type="image/png")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)