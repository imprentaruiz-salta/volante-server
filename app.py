return render_template("panel.html")

@app.route("/qr-mesas")
@app.route("/qr")
def qr_mesas_page():
    """Hoja imprimible con un QR diferente para cada mesa."""
    base_url = request.url_root.rstrip("/")
    return render_template("qr_mesas.html", base_url=base_url)
