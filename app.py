import streamlit as st
import json
import re
import os
from google import genai
from google.genai import types

# ตั้งค่าหน้าเว็บหน้าแรก
st.set_page_config(page_title="ระบบแปลงไฟล์ภาษี หัก ณ ที่จ่าย (High-Speed)", page_icon="📄", layout="wide")

st.title("⚡ ระบบแปลงเอกสารภาษี หัก ณ ที่จ่าย (High-Speed Version)")
st.subheader("เวอร์ชันความเร็วสูงสำหรับ API Key แบบผูกบัตรเครดิต (ลบคอมมาในจำนวนเงินแล้ว)")

# ==========================================
# 1. การตั้งค่าระบบหลังบ้าน (ฝัง API Key สำเร็จรูปถาวร)
# ==========================================
# ฝังคีย์ตัวจริงของคุณลงระบบโดยตรง เพื่อไม่ต้องกรอกหน้าบ้านอีกต่อไป
api_key = "AIzaSyDsIgOPXpTJKuFDSHGzAuDyVMr7s22tZDI"

# แสดงสถานะทางแถบด้านซ้ายแทนกล่องกรอกข้อมูล
st.sidebar.header("🔑 การตั้งค่าระบบ")
st.sidebar.success("🟢 API Key พร้อมใช้งานระดับความเร็วสูงถาวร")

# เตรียมตัวแปรสำหรับจำสถานะข้อมูลในหน้าเว็บเพื่อป้องกันการหายเมื่อกดโหลดไฟล์
if "pnd3_content" not in st.session_state:
    st.session_state.pnd3_content = ""
if "pnd53_content" not in st.session_state:
    st.session_state.pnd53_content = ""
if "pnd3_count" not in st.session_state:
    st.session_state.pnd3_count = 0
if "pnd53_count" not in st.session_state:
    st.session_state.pnd53_count = 0

# หากมีการเปลี่ยน/ลบไฟล์อัปโหลด ให้มีปุ่มล้างค่าเก่าทิ้ง
if st.sidebar.button("🧹 ล้างข้อมูลเก่าเพื่อทำชุดใหม่"):
    st.session_state.pnd3_content = ""
    st.session_state.pnd53_content = ""
    st.session_state.pnd3_count = 0
    st.session_state.pnd53_count = 0
    st.rerun()

# ==========================================
# 2. ฟังก์ชันทำความสะอาดข้อมูลตามกฎเหล็ก สรรพากร
# ==========================================
def clean_text_field(text):
    """ลบเครื่องหมายคำพูดคู่และเดี่ยวออกทั้งหมด ป้องกันระบบสรรพากร Error"""
    if not text:
        return ""
    cleaned = str(text).replace('"', '').replace("'", "")
    return cleaned.strip()

def clean_date_field(date_text):
    """ทำความสะอาดฟิลด์วันที่ ลบช่องว่าง และตรวจสอบให้อยู่ในฟอร์แมต วว/ดด/ปปปป เท่านั้น"""
    if not date_text:
        return ""
    cleaned_date = re.sub(r'\s+', '', str(date_text))
    cleaned_date = cleaned_date.replace('"', '').replace("'", "")
    
    if re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', cleaned_date):
        parts = cleaned_date.split('/')
        day = parts[0].zfill(2)
        month = parts[1].zfill(2)
        year = parts[2]
        return f"{day}/{month}/{year}"
    
    return cleaned_date

def clean_tax_id(tax_id):
    if not tax_id: return ""
    digits = re.sub(r'\D', '', str(tax_id))
    return digits[:13]

def parse_name_and_surname(fullname, taxpayer_type):
    """แยกคำนำหน้า ชื่อ และนามสกุล (แก้ไขบั๊กคำว่า 'นางสาว' และ 'หจก.')"""
    fullname = clean_text_field(fullname)
    prefix, name, surname = "", fullname, ""
    
    # เอาคำยาวขึ้นก่อนเสมอ ป้องกัน 'นางสาว' โดนตัดเหลือแค่ 'นาง'
    prefixes = ["ห้างหุ้นส่วนจำกัด", "บริษัท", "หจก.", "นางสาว", "นาย", "นาง", "น.ส."]
    
    for p in prefixes:
        if fullname.startswith(p):
            prefix = p
            name = fullname[len(p):].strip()
            break
            
    if taxpayer_type == "2": 
        return prefix, name, ""
        
    if " " in name:
        parts = name.split(maxsplit=1)
        name = parts[0].strip()
        surname = parts[1].strip()
    return prefix, name, surname

def format_decimal(amount):
    """ฟังก์ชันเคลียร์ตัวเลข: ลบเครื่องหมายคอมมา (,) และเครื่องหมายคำพูดออกให้หมด เพื่อให้สรรพากรผ่านฉลุย"""
    if not amount:
        return "0.00"
    try:
        clean_num = str(amount).replace(",", "").replace('"', '').replace("'", "").strip()
        return "{:.2f}".format(float(clean_num))
    except (ValueError, TypeError):
        return "0.00"

def map_income_type(raw_type, rate):
    raw_type = clean_text_field(raw_type)
    if "ดัดโค้ง" in raw_type or "ท่อ" in raw_type or "จ้างทำของ" in raw_type or rate == "3.00":
        return "ค่าจ้างทำของ"
    if "ขนส่ง" in raw_type or rate == "1.00":
        return "ค่าขนส่ง"
    if "เช่า" in raw_type or rate == "5.00":
        return "ค่าเช่า"
    return raw_type

# ==========================================
# 3. ส่วนอัปโหลดไฟล์ (Main UI)
# ==========================================
uploaded_files = st.file_uploader(
    "ลากไฟล์ PDF หรือรูปภาพใบหักภาษี ณ ที่จ่ายมาวางตรงนี้ (เวอร์ชัน High-Speed ไม่มีหน่วงเวลา)", 
    type=["pdf", "jpg", "jpeg"], 
    accept_multiple_files=True
)

if uploaded_files:
    if st.button("🚀 เริ่มประมวลผลความเร็วสูง", type="primary"):
        all_extracted_items = []
        client = genai.Client(api_key=api_key)
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for idx, file in enumerate(uploaded_files):
            status_text.text(f"⚡ กำลังประมวลผลอย่างรวดเร็ว ไฟล์ที่ {idx+1}/{len(uploaded_files)}: {file.name} ...")
            file_bytes = file.read()
            mime_type = file.type
            
            prompt = """
            คุณคือระบบ OCR และผู้เชี่ยวชาญด้านภาษีไทย จงอ่านหนังสือรับรองการหักภาษี ณ ที่จ่าย จากไฟล์ที่แนบมา 
            และดึงข้อมูลของผู้ถูกหักภาษีทุกคนออกมาเป็นรายการ (List) ในรูปแบบ JSON โดยมีฟิลด์ดังนี้:
            - tax_id: เลขประจำตัวผู้เสียภาษี 13 หลัก ของผู้ถูกหักภาษี
            - fullname: ชื่อเต็ม (รวมคำนำหน้า เช่น นายสมชาย ใจดี หรือ บริษัท เอ บี จำกัด)
            - address: ที่อยู่ทั้งหมด
            - date: วันเดือนปีที่จ่ายเงิน (ขอฟอร์แมต วว/ดด/ปปปป เป็นปี พ.ศ. เสมอ เช่น 31/01/2569)
            - income_type: ประเภทเงินได้ (เช่น ค่าจ้างทำของ, ค่าขนส่ง)
            - rate: อัตราภาษี (เช่น 1, 3, 5)
            - amount: จำนวนเงินที่จ่าย (ดึงตัวเลขมาทั้งหมด)
            - tax: จำนวนเงินภาษีที่หัก (ดึงตัวเลขมาทั้งหมด)
            - taxpayer_type: ใส่ "1" ถ้าเป็นบุคคลธรรมดา หรือใส่ "2" ถ้าเป็นนิติบุคคล
            """
            
            try:
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=[
                        types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                        prompt
                    ],
                    config=types.GenerateContentConfig(response_mime_type="application/json"),
                )
                
                items = json.loads(response.text)
                if isinstance(items, list):
                    all_extracted_items.extend(items)
                elif isinstance(items, dict):
                    all_extracted_items.append(items)
                    
            except Exception as e:
                st.error(f"เกิดข้อผิดพลาดในการอ่านไฟล์ {file.name}: {e}")
                
            progress_bar.progress((idx + 1) / len(uploaded_files))
            
        status_text.text("✨ ดึงข้อมูลจากทุกเอกสารสำเร็จ! กำลังจัดโครงสร้างไฟล์สรรพากร...")
        
        pnd3_list = []
        pnd53_list = []
        
        for item in all_extracted_items:
            taxpayer_type = str(item.get("taxpayer_type", "1"))
            prefix, name, surname = parse_name_and_surname(item.get("fullname", ""), taxpayer_type)
            
            amount_formatted = format_decimal(item.get("amount", "0"))
            tax_formatted = format_decimal(item.get("tax", "0"))
            rate_formatted = format_decimal(item.get("rate", "3.00"))
            
            income_type = map_income_type(item.get("income_type", ""), rate_formatted)
            address_cleaned = clean_text_field(item.get("address", ""))
            date_cleaned = clean_date_field(item.get("date", ""))
            
            processed_row = {
                "tax_id": clean_tax_id(item.get("tax_id", "")),
                "branch": "00000", "prefix": prefix, "name": name, "surname": surname,
                "address": address_cleaned, "date": date_cleaned,
                "income_type": income_type, "rate": rate_formatted, "amount": amount_formatted,
                "tax": tax_formatted, "condition": "1", "country": "TH", 
                "group_code": "", "old_tax_id": "", "taxpayer_type": taxpayer_type, "filing_type": "01"
            }
            
            if taxpayer_type == "2":
                pnd53_list.append(processed_row)
            else:
                pnd3_list.append(processed_row)
                
        def get_date_key(row):
            try:
                day, month, year = map(int, row["date"].split("/"))
                return (year, month, day)
            except:
                return (9999, 12, 31)
                
        pnd3_list.sort(key=get_date_key)
        pnd53_list.sort(key=get_date_key)
        
        st.session_state.pnd3_content = ""
        for idx, row in enumerate(pnd3_list, 1):
            line = [str(idx), row["tax_id"], row["branch"], row["prefix"], row["name"], row["surname"], row["address"], row["date"], row["income_type"], row["rate"], row["amount"], row["tax"], row["condition"], row["country"], row["group_code"], row["old_tax_id"], row["taxpayer_type"], row["filing_type"]]
            st.session_state.pnd3_content += "|".join(line) + "\n"
            
        st.session_state.pnd53_content = ""
        for idx, row in enumerate(pnd53_list, 1):
            line = [str(idx), row["tax_id"], row["branch"], row["prefix"], row["name"], row["surname"], row["address"], row["date"], row["income_type"], row["rate"], row["amount"], row["tax"], row["condition"], row["country"], row["group_code"], row["old_tax_id"], row["taxpayer_type"], row["filing_type"]]
            st.session_state.pnd53_content += "|".join(line) + "\n"
            
        st.session_state.pnd3_count = len(pnd3_list)
        st.session_state.pnd53_count = len(pnd53_list)
        
        progress_bar.empty()
        status_text.empty()

# ==========================================
# 4. แสดงผลลัพธ์และปุ่มดาวน์โหลดไฟล์หน้าเว็บ
# ==========================================
if st.session_state.pnd3_content or st.session_state.pnd53_content:
    st.success("🎉 ประมวลผลข้อมูลและจัดเรียงวันที่แบบ High-Speed เสร็จสมบูรณ์!")
    col1, col2 = st.columns(2)
    
    with col1:
        st.metric(label="รายการ ภ.ง.ด. 3 (บุคคล)", value=f"{st.session_state.pnd3_count} รายการ")
        if st.session_state.pnd3_content:
            st.download_button(
                label="📥 ดาวน์โหลดไฟล์ pnd3_upload.txt",
                data=st.session_state.pnd3_content,
                file_name="pnd3_upload.txt",
                mime="text/plain",
                key="btn_pnd3"
            )
            st.text_area("ตัวอย่างข้อมูล ภ.ง.ด.3:", value=st.session_state.pnd3_content, height=250, key="txt_pnd3")
            
    with col2:
        st.metric(label="รายการ ภ.ง.ด. 53 (นิติบุคคล)", value=f"{st.session_state.pnd53_count} รายการ")
        if st.session_state.pnd53_content:
            st.download_button(
                label="📥 ดาวน์โหลดไฟล์ pnd53_upload.txt",
                data=st.session_state.pnd53_content,
                file_name="pnd53_upload.txt",
                mime="text/plain",
                key="btn_pnd53"
            )
            st.text_area("ตัวอย่างข้อมูล ภ.ง.ด.53:", value=st.session_state.pnd53_content, height=250, key="txt_pnd53")
