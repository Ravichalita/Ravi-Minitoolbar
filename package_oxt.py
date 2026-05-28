import os
import zipfile

def main():
    src_dir = "mini_toolbar_extension"
    dest_oxt = "MiniToolbar_Updated.oxt"
    
    if os.path.exists(dest_oxt):
        try:
            os.remove(dest_oxt)
        except Exception as e:
            print(f"Error removing existing file: {e}")
            
    print(f"Packaging '{src_dir}' into '{dest_oxt}'...")
    
    with zipfile.ZipFile(dest_oxt, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(src_dir):
            for file in files:
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, src_dir)
                
                # Force forward slashes for zip entries to comply with the ZIP standard
                # and prevent LibreOffice/ZipPackage from raising invalid name exceptions.
                zip_entry_name = rel_path.replace(os.sep, '/')
                
                zipf.write(abs_path, zip_entry_name)
                print(f" -> {zip_entry_name}")
                
    print("Packaging completed successfully!")

if __name__ == "__main__":
    main()
