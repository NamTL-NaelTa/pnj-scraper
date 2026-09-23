import streamlit as st
import pandas as pd
import random
import re
import time
from bs4 import BeautifulSoup
from curl_cffi import requests
from datetime import datetime
import io

# --- 1. THIẾT LẬP TRANG ---
st.set_page_config(page_title="PNJ Lab Data Scraper", page_icon="💎", layout="centered")
st.title("💎 Hệ thống cào dữ liệu PNJ Lab")

# --- 2. CÁC HÀM TIỆN ÍCH (Giữ nguyên logic cũ) ---
def parse_measurement(meas_str):
    if not meas_str: return "", "", ""
    cleaned = meas_str.lower().replace("mm", "").replace("x", " ").replace("-", " ")
    parts = [p for p in cleaned.split() if p.replace(".", "", 1).isdigit()]
    return (parts[0] if len(parts) > 0 else "", 
            parts[1] if len(parts) > 1 else "", 
            parts[2] if len(parts) > 2 else "")

def get_p_span_value(soup, keyword, exclude=None):
    for p in soup.find_all("p"):
        clean_text = " ".join(p.text.split()).upper()
        if exclude and exclude.upper() in clean_text: continue
        if keyword.upper() in clean_text:
            span = p.find("span")
            return span.text.strip() if span else ""
    return ""

def get_table_dict(soup):
    data_dict = {}
    table = soup.find("table", class_=re.compile(r"bg-nen|daquy"))
    if not table:
        for t in soup.find_all("table"):
            if t.find("td", class_=re.compile(r"xanh2")):
                table = t; break
    if not table: return data_dict

    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) >= 2:
            label = " ".join(tds[0].text.split()).upper()
            val = tds[1].text.strip()
            if label and val: data_dict[label] = val
    return data_dict

def get_table_comments(soup):
    table = soup.find("table", class_=re.compile(r"bg-nen|daquy")) or soup.find("table")
    if not table: return ""
    for td in table.find_all("td"):
        clean_text = " ".join(td.text.split()).upper()
        if "COMMENTS" in clean_text or "CHÚ THÍCH" in clean_text:
            span_xanh = td.find("span", class_="xanh")
            if span_xanh and span_xanh.text.strip(): return span_xanh.text.strip()
            text_parts = [elem.text.strip() if hasattr(elem, "text") else elem.strip() 
                          for elem in td.children if elem.name != "strong"]
            return " ".join(filter(None, text_parts)).strip()
    return ""

def find_in_dict(data_dict, *keywords):
    for key, val in data_dict.items():
        for kw in keywords:
            if kw.upper() in key: return val
    return ""

def scrape_pnj_item(session, pnj_code, prod_type, max_retries=1):
    pnj_code = str(int(pnj_code)) if isinstance(pnj_code, (int, float)) else str(pnj_code).strip()
    prod_type_str = str(prod_type).strip().lower()

    if "kc" in prod_type_str or "diamond" in prod_type_str: type_code = 1
    elif "dm" in prod_type_str or "gem" in prod_type_str: type_code = 2
    elif "ct" in prod_type_str or "cẩm thạch" in prod_type_str or "jadeite" in prod_type_str: type_code = 3
    elif "nt" in prod_type_str or "pearl" in prod_type_str: type_code = 4
    else: return "SKIP"

    url = f"https://pnjlab.com.vn/product-result/?ProductID={pnj_code}&type={type_code}"

    for _ in range(max_retries):
        try:
            response = session.get(url, impersonate="chrome120", timeout=15)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                break
            elif response.status_code == 404: return "SKIP"
            elif response.status_code == 403: return None
            else: return None
        except Exception:
            return None
    else: return None

    row_data = {
        "Mã PNJ": pnj_code, "Loại sản phẩm": prod_type, "Tên đá/ Loại ngọc": "",
        "Weight (carat)": "", "size_1": "", "size_2": "", "size_3": "",
        "Màu sắc(Color)": "", "MSC_GIA": "0", "MSC_PNJ": "0", "Đặc điểm": "",
        "Cut Grade": "", "Shape & Cut": "", "Clarity/Transparency": "",
        "Polish/Luster": "", "Symmetry/Surface": "", "Chú thích": "",
    }

    if type_code == 1:
        row_data["Tên đá/ Loại ngọc"] = "Diamond"
        row_data["Weight (carat)"] = (get_p_span_value(soup, "CARAT WEIGHT") or get_p_span_value(soup, "carat")).lower().replace("carat", "").replace("cts", "").strip()
        s1, s2, s3 = parse_measurement(get_p_span_value(soup, "Measurement", exclude="MARGIN"))
        row_data["size_1"], row_data["size_2"], row_data["size_3"] = s1, s2, s3
        row_data["Màu sắc(Color)"] = get_p_span_value(soup, "COLOR GRADE")
        row_data["Cut Grade"] = get_p_span_value(soup, "CUT GRADE")
        row_data["Clarity/Transparency"] = get_p_span_value(soup, "CLARITY GRADE")
        row_data["Shape & Cut"] = get_p_span_value(soup, "Shape & Cut") or get_p_span_value(soup, "Shape")
        row_data["Polish/Luster"] = get_p_span_value(soup, "Polish")
        row_data["Symmetry/Surface"] = get_p_span_value(soup, "Symmetry")
        row_data["MSC_PNJ"] = get_p_span_value(soup, "Inscription") or "0"

        comments_div = soup.find(lambda t: t.name == "div" and "COMMENTS" in t.text.upper() and "title-c" in t.get("class", []))
        if comments_div and (content_div := comments_div.find_next_sibling("div", class_="content")):
            row_data["Chú thích"] = content_div.text.strip()
            if match := re.search(r"GIA\s*(\d+)", row_data["Chú thích"]): row_data["MSC_GIA"] = match.group(1)

        char_div = soup.find(lambda t: t.name == "div" and "CLARITY CHARACTERISTICS" in t.text.upper() and "title-c" in t.get("class", []))
        if char_div and (content_div := char_div.find_next_sibling("div", class_="content")) and content_div.find("p"):
            row_data["Đặc điểm"] = content_div.find("p").text.strip()

    elif type_code in [2, 3, 4]:
        td_dict = get_table_dict(soup)
        row_data["Weight (carat)"] = find_in_dict(td_dict, "WEIGHT", "KHỐI LƯỢNG").lower().replace("cts", "").replace("carat", "").strip()
        s1, s2, s3 = parse_measurement(find_in_dict(td_dict, "MEASUREMENT", "KÍCH THƯỚC"))
        row_data["size_1"], row_data["size_2"], row_data["size_3"] = s1, s2, s3
        row_data["Màu sắc(Color)"] = find_in_dict(td_dict, "COLOR", "MÀU SẮC")
        row_data["Chú thích"] = get_table_comments(soup)

        if type_code == 2:
            row_data["Tên đá/ Loại ngọc"] = find_in_dict(td_dict, "VARIETY", "TÊN ĐÁ")
            row_data["Đặc điểm"] = find_in_dict(td_dict, "GROUP/SPECIES", "SPECIES", "GROUP", "TÊN NHÓM")
            row_data["Shape & Cut"] = find_in_dict(td_dict, "SHAPE - CUTTING STYLE", "SHAPE", "DẠNG CẮT MÀI")
            row_data["Clarity/Transparency"] = find_in_dict(td_dict, "TRANSPARENCY", "ĐỘ TRONG")
        elif type_code == 3:
            row_data["Tên đá/ Loại ngọc"] = find_in_dict(td_dict, "VARIETY", "TÊN ĐÁ", "LOẠI ĐÁ")
            row_data["Đặc điểm"] = find_in_dict(td_dict, "GROUP/SPECIES", "SPECIES", "NHÓM")
            row_data["Shape & Cut"] = find_in_dict(td_dict, "SHAPE", "DẠNG CẮT MÀI", "HÌNH DẠNG")
            row_data["Clarity/Transparency"] = find_in_dict(td_dict, "TRANSPARENCY", "ĐỘ TRONG", "ĐỘ THẤU QUANG")
        elif type_code == 4:
            row_data["Tên đá/ Loại ngọc"] = find_in_dict(td_dict, "PEARL", "LOẠI NGỌC")
            row_data["Đặc điểm"] = find_in_dict(td_dict, "ENVIROMENT", "ENVIRONMENT", "MÔI TRƯỜNG")
            row_data["Shape & Cut"] = find_in_dict(td_dict, "SHARP", "SHAPE", "HÌNH DẠNG")
            row_data["Polish/Luster"] = find_in_dict(td_dict, "LUSTER", "ĐỘ BÓNG")
            row_data["Symmetry/Surface"] = find_in_dict(td_dict, "SURFACE", "BỀ MẶT")

    return row_data

# --- 3. GIAO DIỆN TƯƠNG TÁC ---
st.markdown("### 1. Tải lên danh sách")
uploaded_file = st.file_uploader("Kéo thả file Excel (.xlsx)", type=["xlsx", "xls"])

if uploaded_file is not None:
    df = pd.read_excel(uploaded_file)
    st.write("📋 Bản xem trước (5 dòng đầu):")
    st.dataframe(df.head())

    if st.button("🚀 Kích hoạt thu thập dữ liệu"):
        results = []
        queue = df.to_dict('records')
        pass_count = 1
        session = requests.Session()
        
        # Thiết lập các vùng chứa (containers) để cập nhật UI mượt mà
        status_text = st.empty()
        log_box = st.empty()
        progress_bar = st.progress(0)
        
        total_items = len(queue)
        items_processed = 0
        logs = []

        while len(queue) > 0:
            status_text.markdown(f"**Vòng lặp {pass_count} | Còn lại: {len(queue)} mã**")
            failed_queue = []

            for row in queue:
                pnj_code = row["Mã PNJ"]
                prod_type = row["Loại sản phẩm"]
                
                logs.append(f"🔄 Đang cào: {pnj_code} ({prod_type})...")
                log_box.text("\n".join(logs[-6:])) # Hiển thị 6 dòng log gần nhất

                item_data = scrape_pnj_item(session, pnj_code, prod_type, max_retries=1)

                if item_data == "SKIP":
                    logs[-1] = f"⏭️ Bỏ qua (Lỗi 404/Sai loại): {pnj_code}"
                    items_processed += 1
                elif item_data:
                    logs[-1] = f"✅ Lấy thành công: {pnj_code}"
                    results.append(item_data)
                    items_processed += 1
                else:
                    logs[-1] = f"⏳ Bị chặn/Lỗi mạng (Chờ duyệt lại): {pnj_code}"
                    failed_queue.append(row)

                log_box.text("\n".join(logs[-6:]))
                progress_bar.progress(min(items_processed / total_items, 1.0))
                time.sleep(random.uniform(1.5, 3.0))

            queue = failed_queue
            if len(queue) > 0:
                logs.append(f"💤 Tạm nghỉ 10s trước khi cào lại {len(queue)} mã lỗi...")
                log_box.text("\n".join(logs[-6:]))
                time.sleep(10)
                pass_count += 1

        st.success("🎉 Hoàn tất 100%!")
        
        # Ghi dữ liệu vào RAM và cấu hình format Excel
        df_result = pd.DataFrame(results)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df_result.to_excel(writer, index=False, sheet_name="Data_PNJ")
            worksheet = writer.sheets["Data_PNJ"]
            for col in worksheet.columns:
                max_len = max((len(str(cell.value)) for cell in col if cell.value is not None), default=0)
                worksheet.column_dimensions[col[0].column_letter].width = max(max_len + 4, 12)
        
        # Trả về file cho trình duyệt
        st.download_button(
            label="⬇️ Tải file kết quả (Excel)",
            data=output.getvalue(),
            file_name=f"KetQua_PNJ_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )