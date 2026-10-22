import os

if os.getenv('LIFEOS_STANDALONE') == '1':
    from lifeos_app import create_app
    app = create_app()
else:
    import people_app
    import tracking_patch
    import mr_rich_menu
    tracking_patch.apply(people_app)
    app = people_app.app
    mr_rich_menu.start(app)
    if os.getenv('LIFEOS_CLIENTS_FILE'):
        from lifeos_app import install_clients
        install_clients(app, shared=True)
        from lifeos_setup import install_setup_clients
        install_setup_clients(app, os.environ['LIFEOS_CLIENTS_FILE'])

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
