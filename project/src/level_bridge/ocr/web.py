"""Loopback-first Flask interface. No remote assets or browser camera dependency."""
import secrets
from pathlib import Path

from . import OCRError
from .service import ScanService


def create_app(cfg, service=None):
    from flask import Flask, jsonify, request, render_template, send_file, Response, session
    from ..model_runtime import RuntimeUnavailable
    from ..passage_processor import PassageError
    from ..lesson_pack import PackError
    app = Flask(__name__)
    app.secret_key = secrets.token_hex(32)
    app.config.update(MAX_CONTENT_LENGTH=cfg.app.get('ocr', {}).get('max_bytes', 12*1024*1024)+65536,
                      TRUSTED_HOSTS=cfg.app.get('ocr', {}).get('trusted_hosts', ['127.0.0.1', 'localhost', '[::1]']),
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Strict')
    store = service or ScanService(cfg)

    @app.before_request
    def protect():
        if not cfg.app.get('ocr', {}).get('enabled', False):
            return jsonify(error='OCR is disabled in config/config.yaml'), 403
        if request.method == 'POST' and (not session.get('token') or not secrets.compare_digest(request.headers.get('X-CSRF-Token',''), session['token'])):
            return jsonify(error='Reload the local page before continuing.'), 403

    @app.after_request
    def headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; frame-ancestors 'none'"
        return response

    @app.errorhandler(OCRError)
    @app.errorhandler(RuntimeUnavailable)
    @app.errorhandler(PassageError)
    @app.errorhandler(PackError)
    def failure(exc):
        return jsonify(error=str(exc)), 400

    @app.errorhandler(413)
    def oversized(exc):
        return jsonify(error='Image exceeds upload size limit.'), 413

    @app.get('/')
    def home():
        session.setdefault('token', secrets.token_hex(32))
        return render_template('scan.html', token=session['token'])

    @app.get('/preview')
    def preview():
        from .camera import preview
        frames = preview(store.options.get('camera_index'))
        first = next(frames)  # detect camera errors before sending headers
        def stream():
            try:
                yield first
                yield from frames
            finally:
                frames.close()
        return Response(stream(), mimetype='multipart/x-mixed-replace; boundary=frame')

    @app.get('/read')
    @app.get('/math')
    def math_page():
        session.setdefault('token', secrets.token_hex(32))
        version=str((Path(__file__).parent/'static'/'reader.js').stat().st_mtime_ns)
        return render_template('reader.html', token=session['token'], asset_version=version)

    @app.get('/math/example')
    def math_example():
        scan_id=store.options.get('math',{}).get('example_scan_id','')
        return original(scan_id)

    @app.post('/math/recognize')
    def math_recognize():
        raise OCRError('Equation conversion is disabled. Use the Tesseract text reader.')

    @app.post('/math/extract')
    @app.post('/upload')
    def upload():
        image = request.files.get('image')
        if image is None:
            raise OCRError('Select an image file.')
        with store.lock:
            return jsonify(store.upload(image.read(store.options.get('max_bytes', 12*1024*1024)+1), image.filename))

    @app.post('/capture')
    def capture():
        from .camera import capture_image
        with store.lock:
            path = capture_image(store.options.get('camera_index'), store.root / 'captures',
                                 warmup_s=store.options.get('camera_warmup_s', 1.5))
            try:
                return jsonify(store.upload(path.read_bytes(), path.name))
            finally:
                path.unlink(missing_ok=True)

    @app.get('/scan/<scan_id>/image')
    def original(scan_id):
        record = store.read(scan_id)
        path = Path(record['original_image']).resolve()
        if path.parent != store.root / 'captures':
            raise OCRError('Invalid image path.')
        return send_file(path)

    @app.post('/scan/<scan_id>/<action>')
    def action(scan_id, action):
        body = request.get_json(silent=True) or {}
        with store.lock:
            if action == 'edit':
                result = store.edit(scan_id, str(body.get('text', '')))
            elif action == 'confirm':
                result = store.confirm(scan_id, str(body.get('text', '')), body.get('checked'))
            elif action == 'rerun':
                result = store.rerun(scan_id)
            elif action == 'build':
                backend = body.get('backend') or None
                if backend not in (None, 'template'):
                    raise OCRError('Use the configured model or explicit template demo.')
                result = store.prepare(scan_id, backend)
            elif action == 'delete':
                store.delete(scan_id)
                result = {'deleted': True}
            else:
                raise OCRError('Unknown action.')
            return jsonify(result)
    return app
