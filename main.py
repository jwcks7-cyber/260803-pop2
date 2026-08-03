# -*- coding: utf-8 -*-
"""
전국 시군구별 고령화 지도 (65세 이상 인구 비율)
- 스트림릿 클라우드 배포용 앱
- 초보자를 위해 각 단계마다 한국어 주석을 달아 두었습니다.
"""

import pandas as pd
import numpy as np
import requests
import streamlit as st
import plotly.express as px

# -----------------------------------------------------------------
# 0. 페이지 기본 설정
# -----------------------------------------------------------------
st.set_page_config(page_title="전국 고령화 지도", layout="wide")

st.title("🗺️ 전국 시군구 고령화 지도")
st.caption("시군구별 65세 이상 인구 비율(고령화율)을 5단계로 나누어 표시합니다.")

# 데이터 주소
POP_URL = "https://raw.githubusercontent.com/greatsong/modudata/main/data/population_yearly.csv.gz"
GEO_URL = "https://raw.githubusercontent.com/greatsong/modudata/main/data/boundaries/sigungu_kr.geojson"


# -----------------------------------------------------------------
# 1. 인구 데이터 불러오기 (캐시 처리: 앱이 다시 실행돼도 매번 새로 안 받도록)
# -----------------------------------------------------------------
@st.cache_data(show_spinner="인구 데이터를 불러오는 중...")
def load_population():
    # '코드' 열은 숫자가 아니라 이름표(문자열)이므로 dtype=str 로 읽어서
    # 앞자리에 붙은 0이 사라지지 않도록 합니다.
    df = pd.read_csv(POP_URL, compression="gzip", dtype={"코드": str})
    return df


# -----------------------------------------------------------------
# 2. 시군구 경계 GeoJSON 불러오기
# -----------------------------------------------------------------
@st.cache_data(show_spinner="지도 경계 데이터를 불러오는 중...")
def load_geojson():
    res = requests.get(GEO_URL)
    res.raise_for_status()
    return res.json()


pop_raw = load_population()
geo = load_geojson()

# -----------------------------------------------------------------
# 3. 가장 최신 연도만 골라내기
# -----------------------------------------------------------------
latest_year = pop_raw["연도"].max()
df = pop_raw[pop_raw["연도"] == latest_year].copy()

# -----------------------------------------------------------------
# 4. '코드'에서 앞 5자리를 잘라 시군구 코드를 새로 만듭니다.
#    (읍·면·동 단위 데이터를 시군구 단위로 묶기 위한 열쇠입니다)
# -----------------------------------------------------------------
df["시군구코드"] = df["코드"].astype(str).str[:5]

# -----------------------------------------------------------------
# 5. 나이별 인구 열 중에서 '계_'로 시작하는(남녀 합계) 열만 골라냅니다.
#    그리고 그중 65세 이상에 해당하는 열만 따로 추립니다.
# -----------------------------------------------------------------
def 나이_추출(col_name: str) -> int:
    """'계_37세' -> 37, '계_100세 이상' -> 100 처럼 나이 숫자만 뽑아내는 함수"""
    나이문자 = col_name.replace("계_", "").replace("세", "").strip()
    if "이상" in 나이문자:
        return 100
    return int(나이문자)


전체나이_열 = [c for c in df.columns if c.startswith("계_")]
고령나이_열 = [c for c in 전체나이_열 if 나이_추출(c) >= 65]

# 읍면동 단위로 총인구, 고령인구를 먼저 계산합니다.
df["총인구"] = df[전체나이_열].sum(axis=1)
df["고령인구"] = df[고령나이_열].sum(axis=1)

# -----------------------------------------------------------------
# 6. 읍·면·동 데이터를 시군구코드 기준으로 합쳐서(groupby) 시군구 단위로 만듭니다.
# -----------------------------------------------------------------
sigungu_df = (
    df.groupby("시군구코드")
    .agg(
        시도=("시도", "first"),
        시군구=("시군구", "first"),
        총인구=("총인구", "sum"),
        고령인구=("고령인구", "sum"),
    )
    .reset_index()
)

# 고령화율(%) 계산
sigungu_df["고령화율"] = (sigungu_df["고령인구"] / sigungu_df["총인구"]) * 100

# -----------------------------------------------------------------
# 7. 고령화율을 5단계 구간으로 나눕니다. (경계값: 19% · 23% · 28% · 38%)
# -----------------------------------------------------------------
구간_경계 = [-0.01, 19, 23, 28, 38, 100]
구간_이름 = ["19% 미만", "19%~23%", "23%~28%", "28%~38%", "38% 이상"]

sigungu_df["구간"] = pd.cut(
    sigungu_df["고령화율"], bins=구간_경계, labels=구간_이름
)

# 낮은 단계는 옅은 색, 높은 단계는 진한 색이 되도록 색상을 직접 지정합니다.
구간_색상 = {
    "19% 미만": "#fee5d9",
    "19%~23%": "#fcbba1",
    "23%~28%": "#fb6a4a",
    "28%~38%": "#de2d26",
    "38% 이상": "#67000d",
}

# 지도에 표시할 때 보기 좋게 소수점 한 자리로 반올림한 열을 하나 더 만들어 둡니다.
sigungu_df["고령화율_표시"] = sigungu_df["고령화율"].round(1)

# -----------------------------------------------------------------
# 8. 단계구분도(Choropleth) 그리기
#    - 지역은 이름이 아니라 '코드'로 맞춥니다 (이름 중복 문제 방지)
#    - 배경 지도(타일)는 끄고 경계선만 보이도록 설정합니다.
# -----------------------------------------------------------------
fig = px.choropleth(
    sigungu_df,
    geojson=geo,
    locations="시군구코드",
    featureidkey="properties.코드",
    color="구간",
    category_orders={"구간": 구간_이름},
    color_discrete_map=구간_색상,
    hover_name="시군구",
    hover_data={
        "시군구코드": False,
        "시도": True,
        "고령화율_표시": True,
        "구간": False,
    },
    labels={"고령화율_표시": "고령화율(%)", "시도": "시도", "구간": "구간"},
)

# 지도 경계선만 보이게, 배경 타일/바다/육지 색은 모두 꺼 줍니다.
fig.update_geos(
    visible=False,
    fitbounds="locations",
    showcountries=False,
    showland=False,
    showocean=False,
    showlakes=False,
    bgcolor="rgba(0,0,0,0)",
)

# 시군구 경계선을 또렷하게 표시합니다.
fig.update_traces(marker_line_color="white", marker_line_width=0.6)

fig.update_layout(
    margin=dict(l=0, r=0, t=30, b=0),
    legend_title_text="고령화율 구간",
    height=750,
)

st.subheader(f"📍 {latest_year}년 기준 시군구별 고령화율")
st.plotly_chart(fig, use_container_width=True)

# -----------------------------------------------------------------
# 9. 고령화율 높은 지역 10곳 / 낮은 지역 10곳을 표로 나란히 보여줍니다.
# -----------------------------------------------------------------
표시_열 = {"시도": "시도", "시군구": "시군구", "고령화율_표시": "고령화율(%)"}

상위10 = (
    sigungu_df.sort_values("고령화율", ascending=False)
    .head(10)[["시도", "시군구", "고령화율_표시"]]
    .rename(columns=표시_열)
    .reset_index(drop=True)
)
상위10.index = 상위10.index + 1

하위10 = (
    sigungu_df.sort_values("고령화율", ascending=True)
    .head(10)[["시도", "시군구", "고령화율_표시"]]
    .rename(columns=표시_열)
    .reset_index(drop=True)
)
하위10.index = 하위10.index + 1

col1, col2 = st.columns(2)

with col1:
    st.markdown("### 🔺 고령화율 높은 지역 TOP 10")
    st.dataframe(
        상위10.style.format({"고령화율(%)": "{:.1f}"}),
        use_container_width=True,
    )

with col2:
    st.markdown("### 🔻 고령화율 낮은 지역 TOP 10")
    st.dataframe(
        하위10.style.format({"고령화율(%)": "{:.1f}"}),
        use_container_width=True,
    )

st.caption("데이터 출처: population_yearly.csv.gz / sigungu_kr.geojson (greatsong/modudata)")
