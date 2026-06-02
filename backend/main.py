from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse
from pypdf import PdfWriter, PdfReader
import fitz  # PyMuPDF
import io
import json
import base64
import os

app = FastAPI(title="PDF Magic Toolkit API")

# เปิดใช้งาน CORS เพื่อให้หน้าบ้านติดต่อหลังบ้านได้สะดวก
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """
    เซิร์ฟหน้าเว็บหลัก index.html ออกไปเมื่อผู้ใช้งานเปิดเข้าลิงก์หลักของเว็บแอปพลิเคชัน
    """
    html_path = os.path.join(os.path.dirname(__file__), "../frontend/index.html")
    if not os.path.exists(html_path):
        html_path = os.path.join(os.getcwd(), "frontend/index.html")
        
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>ไม่พบไฟล์หน้าบ้าน (frontend/index.html) ในระบบ</h1>"

@app.post("/api/preview")
async def get_pdf_preview(file: UploadFile = File(...)):
    """
    รับไฟล์ PDF และแปลงทุกหน้ากระดาษเป็นภาพพรีวิว (Base64 PNG) ส่งกลับไปให้หน้าบ้านแสดงผล
    """
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="กรุณาอัปโหลดเฉพาะไฟล์ PDF เท่านั้น")
    
    try:
        file_bytes = await file.read()
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        pages_data = []
        
        for idx in range(len(doc)):
            page = doc.load_page(idx)
            # เรนเดอร์หน้าพรีวิวเป็นรูปภาพขนาดเบา (DPI 75)
            pix = page.get_pixmap(dpi=75)
            img_data = pix.tobytes("png")
            base64_img = base64.b64encode(img_data).decode('utf-8')
            
            pages_data.append({
                "page_index": idx,
                "image": f"data:image/png;base64,{base64_img}"
            })
            
        doc.close()
        return {
            "filename": file.filename,
            "total_pages": len(pages_data),
            "pages": pages_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาดในการอ่านไฟล์ PDF: {str(e)}")

@app.post("/api/merge")
async def merge_pdf_pages(
    files: list[UploadFile] = File(...),
    order: str = Form(...)  # รับ JSON String ระบุลำดับหน้า เช่น [{"filename": "a.pdf", "page_index": 0}, ...]
):
    """
    รับไฟล์ทั้งหมดพร้อมกับลำดับหน้าใหม่ที่ถูกลากวางสลับแล้ว จากนั้นทำการรวบรวมประกอบเป็นไฟล์ PDF ใหม่ส่งกลับไปให้ดาวน์โหลด
    """
    try:
        # แปลงข้อความ JSON ลำดับหน้ากลับมาเป็น Python List
        page_orders = json.loads(order)
        
        # เก็บข้อมูลไฟล์ PDF ในลักษณะของดิกชันนารีเพื่อความสะดวกในการเข้าถึง
        pdf_readers = {}
        for f in files:
            file_bytes = await f.read()
            pdf_readers[f.filename] = PdfReader(io.BytesIO(file_bytes))
            
        # สร้าง PDF เล่มใหม่ตามลำดับที่ส่งมาจากหน้าบ้าน
        writer = PdfWriter()
        for item in page_orders:
            fname = item.get("filename")
            p_idx = item.get("page_index")
            
            if fname in pdf_readers:
                reader = pdf_readers[fname]
                if 0 <= p_idx < len(reader.pages):
                    writer.add_page(reader.pages[p_idx])
                    
        # เขียนไฟล์ลงหน่วยความจำชั่วคราวเพื่อส่งออก
        output_buffer = io.BytesIO()
        writer.write(output_buffer)
        writer.close()
        output_buffer.seek(0)
        
        return StreamingResponse(
            output_buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=merged_output.pdf"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาดในการรวมไฟล์: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
