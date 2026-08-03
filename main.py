# -*- coding: utf-8 -*-
"""
전국 시군구별 고령화 지도 (65세 이상 인구 비율)
- 스트림릿 클라우드 배포용 앱
- 연도를 슬라이더로 골라 그 해 기준 지도를 볼 수 있습니다.
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

# 색 구간은 연도가 바뀌어도 그대로 고정합니다. (해마다 색을 비교할 수 있도록)
구간_경계 = [-0.01, 19, 23, 28, 38, 100]
구간_이름 = ["19% 미만", "19%~23%", "23%~28%", "28%~38%", "38% 이상"]
구간_색상 = {
    "19% 미만": "#fee5d9",
    "19%~23%": "#fcbba1",
    "23%~28%": "#fb6a4a",
    "28%~38%": "#de2d26",
    "38% 이상": "#67000d",
    "자료 없음": "#cccccc",  # 경계 코드가 안 맞아 비교할 인구 데이터가 없는 지역
}


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


def 나이_추출(col_name: str) -> int:
    """'계_37세' -> 37, '계_100세 이상' -> 100 처럼 나이 숫자만 뽑아내는 함수"""
    나이문자 = col_name.replace("계_", "").replace("세", "").strip()
    if "이상" in 나이문자:
        return 100
    return int(나이문자)


def 시군구코드_보정(code: str) -> str:
    """
    행정구역 개편으로 옛 시도 코드가 남아 있는 경우를 최신 코드로 바꿔 줍니다.
    - 옛 강원 코드 42 -> 51
    - 옛 전북 코드 45 -> 52
    - 군위군 47720(옛 경북 소속) -> 27720(현재 대구 소속)
    """
    if code == "47720":
        return "27720"
    if code[:2] == "42":
        return "51" + code[2:]
    if code[:2] == "45":
        return "52" + code[2:]
    return code


# -----------------------------------------------------------------
# 3. 원본 데이터 불러오기 + 나이 열 계산은 연도와 무관하게 한 번만 수행
# -----------------------------------------------------------------
pop_raw = load_population()
geo = load_geojson()

# GeoJSON에 실제로 들어 있는 시군구 코드 목록을 미리 만들어 둡니다.
geo_df = pd.DataFrame(
    [
        {
            "시군구코드": f["properties"]["코드"],
            "시도_geo": f["properties"]["시도"],
            "시군구_geo": f["properties"]["시군구"],
        }
        for f in geo["features"]
    ]
)

# 나이별 인구 열 중에서 '계_'로 시작하는(남녀 합계) 열만 골라냅니다.
전체나이_열 = [c for c in pop_raw.columns if c.startswith("계_")]
고령나이_열 = [c for c in 전체나이_열 if 나이_추출(c) >= 65]

pop_raw["시군구코드"] = pop_raw["코드"].astype(str).str[:5].apply(시군구코드_보정)
pop_raw["총인구"] = pop_raw[전체나이_열].sum(axis=1)
pop_raw["고령인구"] = pop_raw[고령나이_열].sum(axis=1)

# -----------------------------------------------------------------
# 4. 연도 슬라이더
# -----------------------------------------------------------------
연도목록 = sorted(pop_raw["연도"].unique())
선택연도 = st.slider(
    "연도 선택",
    min_value=int(min(연도목록)),
    max_value=int(max(연도목록)),
    value=int(max(연도목록)),
    step=1,
)

# -----------------------------------------------------------------
# 4-1. '성남시보다 65세 이상 인구 많은 지역' 강조 버튼
#      버튼을 누를 때마다 강조 켜기/끄기가 번갈아 바뀝니다.
# -----------------------------------------------------------------
if "성남시_강조" not in st.session_state:
    st.session_state.성남시_강조 = False

if st.button("🟣 성남시보다 65세 이상 인구 많은 지역 보기"):
    st.session_state.성남시_강조 = not st.session_state.성남시_강조

# -----------------------------------------------------------------
# 5. 선택한 연도의 데이터만 골라 시군구 단위로 합칩니다.
# -----------------------------------------------------------------
df_year = pop_raw[pop_raw["연도"] == 선택연도]

sigungu_df = (
    df_year.groupby("시군구코드")
    .agg(
        시도=("시도", "first"),
        시군구=("시군구", "first"),
        총인구=("총인구", "sum"),
        고령인구=("고령인구", "sum"),
    )
    .reset_index()
)
sigungu_df["고령화율"] = (sigungu_df["고령인구"] / sigungu_df["총인구"]) * 100
sigungu_df["고령화율_표시"] = sigungu_df["고령화율"].round(1)

# -----------------------------------------------------------------
# 5-1. 강조 버튼이 켜져 있으면, 성남시의 65세 이상 인구(고령인구)를 구합니다.
#      성남시는 수정구·중원구·분당구로 나뉘어 있을 수 있어 이름이
#      '성남시'로 시작하는 행을 모두 더합니다.
# -----------------------------------------------------------------
성남시_고령인구 = None
if st.session_state.성남시_강조:
    성남시_행 = sigungu_df[sigungu_df["시군구"].str.startswith("성남시")]
    if len(성남시_행) > 0:
        성남시_고령인구 = 성남시_행["고령인구"].sum()
    else:
        st.info(f"{선택연도}년 데이터에서 '성남시'를 찾을 수 없어 비교할 수 없습니다.")

# -----------------------------------------------------------------
# 6. GeoJSON 기준으로 왼쪽 조인 -> 경계는 있는데 인구 데이터가 없는 지역은
#    '자료 없음'(회색)으로 표시합니다.
# -----------------------------------------------------------------
map_df = geo_df.merge(sigungu_df, on="시군구코드", how="left")

map_df["구간"] = pd.cut(
    map_df["고령화율"], bins=구간_경계, labels=구간_이름
)
# 인구 데이터가 없어서 구간이 NaN인 경우 '자료 없음'으로 채웁니다.
map_df["구간"] = map_df["구간"].astype("object")
map_df.loc[map_df["고령화율"].isna(), "구간"] = "자료 없음"

# 강조 버튼이 켜져 있으면, 성남시보다 65세 이상 인구가 많은 지역은
# 원래 색 구간을 덮어쓰고 보라색 전용 구간으로 표시합니다.
if 성남시_고령인구 is not None:
    강조대상 = map_df["고령인구"] > 성남시_고령인구
    map_df.loc[강조대상, "구간"] = "성남시보다 고령인구 많음"

# 지도에 표시할 시도/시군구 이름은 GeoJSON 쪽 이름을 기본으로 쓰고,
# 비어 있으면 인구 데이터 쪽 이름으로 채웁니다.
map_df["시도_표시"] = map_df["시도"].fillna(map_df["시도_geo"])
map_df["시군구_표시"] = map_df["시군구"].fillna(map_df["시군구_geo"])

# -----------------------------------------------------------------
# 7. 인구 데이터에는 있지만 GeoJSON 경계와 끝내 안 맞는 지역을 찾아 안내합니다.
#    (보정 후에도 매칭이 안 되는, 즉 지도에 아예 그릴 수 없는 지역)
# -----------------------------------------------------------------
안맞는지역 = sigungu_df[~sigungu_df["시군구코드"].isin(geo_df["시군구코드"])]

# -----------------------------------------------------------------
# 8. 단계구분도(Choropleth) 그리기
#    - 지역은 이름이 아니라 '코드'로 맞춥니다 (이름 중복 문제 방지)
#    - 배경 지도(타일)는 끄고 경계선만 보이도록 설정합니다.
#    - 색 구간 순서는 항상 동일하게 고정합니다.
# -----------------------------------------------------------------
범례순서 = 구간_이름 + ["자료 없음"]
표시_색상표 = 구간_색상.copy()

# 강조 버튼이 켜져 있을 때만 보라색 구간을 범례와 색상표에 추가합니다.
if 성남시_고령인구 is not None:
    표시_색상표["성남시보다 고령인구 많음"] = "#8e44ad"
    범례순서 = 범례순서 + ["성남시보다 고령인구 많음"]

fig = px.choropleth(
    map_df,
    geojson=geo,
    locations="시군구코드",
    featureidkey="properties.코드",
    color="구간",
    category_orders={"구간": 범례순서},
    color_discrete_map=표시_색상표,
    hover_name="시군구_표시",
    hover_data={
        "시군구코드": False,
        "시도_표시": True,
        "고령화율_표시": True,
        "구간": False,
    },
    labels={"고령화율_표시": "고령화율(%)", "시도_표시": "시도", "구간": "구간"},
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

st.subheader(f"📍 {선택연도}년 기준 시군구별 고령화율")
if 성남시_고령인구 is not None:
    st.caption(
        f"🟣 보라색 = {선택연도}년 성남시 65세 이상 인구({성남시_고령인구:,.0f}명)보다 "
        f"65세 이상 인구가 많은 지역"
    )
st.plotly_chart(fig, use_container_width=True)

# 지도와 비교할 수 없는(경계 코드가 끝내 안 맞는) 지역 안내 문구
if len(안맞는지역) > 0:
    안맞는_이름목록 = "，".join(
        (안맞는지역["시도"] + " " + 안맞는지역["시군구"]).tolist()
    )
    st.warning(
        f"⚠️ {선택연도}년 데이터 중 다음 지역은 행정구역 개편으로 경계 파일과 코드가 맞지 않아 "
        f"지도에 표시하지 못했습니다: {안맞는_이름목록}"
    )

# -----------------------------------------------------------------
# 9. 고령화율 높은 지역 10곳 / 낮은 지역 10곳을 표로 나란히 보여줍니다.
#    (실제 인구 데이터가 있는 지역만 대상으로 합니다)
# -----------------------------------------------------------------
표시_열 = {"시도": "시도", "시군구": "시군구", "고령화율_표시": "고령화율(%)"}

순위대상 = sigungu_df.dropna(subset=["고령화율"])

상위10 = (
    순위대상.sort_values("고령화율", ascending=False)
    .head(10)[["시도", "시군구", "고령화율_표시"]]
    .rename(columns=표시_열)
    .reset_index(drop=True)
)
상위10.index = 상위10.index + 1

하위10 = (
    순위대상.sort_values("고령화율", ascending=True)
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
