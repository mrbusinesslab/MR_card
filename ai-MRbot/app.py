import people_app
import tracking_patch

tracking_patch.apply(people_app)
app = people_app.app

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
