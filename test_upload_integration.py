import requests

# Minimal integration test for file upload endpoint

def test_upload_zip():
    url = "http://localhost:8000/upload/file"
    test_zip = "test_upload.zip"
    # Create a small dummy zip file
    with open(test_zip, "wb") as f:
        f.write(b"PK\x03\x04testdata")
    files = {"file": (test_zip, open(test_zip, "rb"), "application/zip")}
    response = requests.post(url, files=files)
    print("Status code:", response.status_code)
    print("Response:", response.json())
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "metrics" in data
    print("Upload test passed.")

if __name__ == "__main__":
    test_upload_zip()
