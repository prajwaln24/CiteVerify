
import os

# Create a folder for test PDFs
os.makedirs("CiteVerify_Test_Files", exist_ok=True)

folder = "CiteVerify_Test_Files"

# 1. Fake PDF
with open(f"{folder}/fake.pdf", "wb") as f:
    f.write(b"This is not a real PDF file.")

# 2. Empty PDF
with open(f"{folder}/empty.pdf", "wb") as f:
    f.write(b"")

# 3. Corrupted PDF
with open(f"{folder}/corrupted.pdf", "wb") as f:
    f.write(
        b"%PDF-1.7\n"
        b"This is a damaged PDF file.\n"
        b"Invalid PDF structure."
    )

print("SUCCESS! All 3 test files created.")

print("Location:", os.path.abspath(folder))