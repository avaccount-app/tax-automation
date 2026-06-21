import sys
import os

from PyQt6.QtWidgets import *

from ocr import read_file
from classify import classify
from extract import extract_data
from validate import validate
from export_rdprep import export_rdprep



records=[]



class Main(QMainWindow):

    def __init__(self):

        super().__init__()

        self.setWindowTitle(
            "RD50 OCR V5.2"
        )

        self.resize(900,600)


        btn=QPushButton(
            "เลือก Folder 50 ทวิ"
        )

        exp=QPushButton(
            "สร้าง RD Prep CSV"
        )


        self.table=QTableWidget()


        layout=QVBoxLayout()

        layout.addWidget(btn)
        layout.addWidget(exp)
        layout.addWidget(self.table)


        w=QWidget()
        w.setLayout(layout)

        self.setCentralWidget(w)


        btn.clicked.connect(
            self.scan
        )


        exp.clicked.connect(
            lambda: export_rdprep(records)
        )




    def scan(self):

        global records

        records=[]


        folder=QFileDialog.getExistingDirectory(
            self
        )


        for f in os.listdir(folder):

            if f.lower().endswith(
                (".pdf",".jpg",".png")
            ):


                path=os.path.join(
                    folder,f
                )


                text=read_file(path)


                print(
                    "========== OCR =========="
                )

                print(text)

                print(
                    "=========================="
                )



                row=extract_data(text)


                row["type"]=classify(text)

                row["file"]=f


                row["status"]=validate(row)


                records.append(row)



        self.show_table()




    def show_table(self):

        self.table.setRowCount(
            len(records)
        )

        self.table.setColumnCount(6)


        headers=[
            "File",
            "ประเภท",
            "ชื่อ",
            "เงิน",
            "ภาษี",
            "สถานะ"
        ]


        self.table.setHorizontalHeaderLabels(
            headers
        )


        for i,r in enumerate(records):

            values=[

                r.get("file",""),
                r.get("type",""),
                r.get("name",""),
                r.get("amount",0),
                r.get("tax",0),
                r.get("status","")

            ]


            for j,v in enumerate(values):

                self.table.setItem(
                    i,
                    j,
                    QTableWidgetItem(str(v))
                )




app=QApplication(sys.argv)

win=Main()

win.show()

sys.exit(
    app.exec()
)