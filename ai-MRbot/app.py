import os

if os.getenv('LIFEOS_STANDALONE') == '1':
    from lifeos_app import create_app
    app = create_app()
else:
    import people_app
    import tracking_patch
    tracking_patch.apply(people_app)
    app = people_app.app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
