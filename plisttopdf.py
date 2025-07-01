import plistlib
import json
import os
import tkinter as tk
from tkinter import filedialog, messagebox
from reportlab.lib.pagesizes import letter, landscape
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch


def dict_to_lines(data):
    """
    Convert dictionary (or list) into a list of formatted text lines
    with JSON-like representation.
    """
    json_str = json.dumps(data, indent=4, ensure_ascii=False)
    return json_str.splitlines()


def plist_to_pdf(input_path, output_path, landscape_mode=False):
    # Load plist
    with open(input_path, 'rb') as fp:
        plist_data = plistlib.load(fp)

    # Prepare PDF
    page_size = letter
    if landscape_mode:
        page_size = landscape(letter)
    c = canvas.Canvas(output_path, pagesize=page_size)
    width, height = page_size
    margin = inch
    text = c.beginText(margin, height - margin)
    text.setFont("Courier", 10)
    text.setLeading(14)

    # Convert data to lines
    lines = dict_to_lines(plist_data)
    for line in lines:
        # Wrap long lines
        if len(line) > 100:
            for part in [line[i:i+100] for i in range(0, len(line), 100)]:
                text.textLine(part)
        else:
            text.textLine(line)
        # New page if needed
        if text.getY() < margin:
            c.drawText(text)
            c.showPage()
            text = c.beginText(margin, height - margin)
            text.setFont("Courier", 10)
            text.setLeading(14)

    c.drawText(text)
    c.save()


def main():
    # Initialize hidden root for dialogs
    root = tk.Tk()
    root.withdraw()

    # Base directory for dialogs
    base_dir = os.getcwd()

    # Select plist file (show .plist and allow all files)
    input_path = filedialog.askopenfilename(
        title="Select plist file",
        initialdir=base_dir,
        filetypes=[
            ("Property List (*.plist)", "*.plist"),
            ("All files", "*.*")
        ]
    )
    if not input_path:
        return

    # Ask for landscape orientation
    landscape_mode = messagebox.askyesno(
        title="Orientation",
        message="Use landscape orientation for the PDF?"
    )

    # Choose output PDF location (show .pdf and allow all files)
    default_name = os.path.splitext(os.path.basename(input_path))[0] + '.pdf'
    output_path = filedialog.asksaveasfilename(
        title="Save PDF as",
        initialdir=base_dir,
        initialfile=default_name,
        defaultextension=".pdf",
        filetypes=[
            ("PDF File (*.pdf)", "*.pdf"),
            ("All files", "*.*")
        ]
    )
    if not output_path:
        return

    # Convert and notify
    try:
        plist_to_pdf(input_path, output_path, landscape_mode)
        messagebox.showinfo("Success", f"PDF generated:\n{output_path}")
    except Exception as e:
        messagebox.showerror("Error", f"Failed to generate PDF:\n{e}")

if __name__ == '__main__':
    main()
