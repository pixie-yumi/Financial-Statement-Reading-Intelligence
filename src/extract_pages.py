import pypdf

reader = pypdf.PdfReader(r"C:\Users\ASUS\finsight-statement-id\data\JS BankLtd.pdf")
writer = pypdf.PdfWriter()

for page_num in [182, 183, 184]:
    writer.add_page(reader.pages[page_num])

with open("js_bank_consolidated_bs.pdf", "wb") as f:
    writer.write(f)