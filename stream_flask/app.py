from hashlib import sha256
from dotenv import load_dotenv

load_dotenv()
from shutil import rmtree
import logging
import subprocess
import pysrt
from celery import Celery
import os
import boto3
from botocore.exceptions import ClientError
from functools import wraps
from flask import (
    Flask,
    redirect,
    request,
    render_template,
    make_response,
    url_for,
    flash,
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s: %(levelname)s: %(message)s"
)


def make_celery(app):
    celery = Celery(app.name)
    celery.conf.update(app.config["CELERY_CONFIG"])

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    return celery


###############
## Flask app ##
###############


app = Flask(__name__)
app.config.update(
    CELERY_CONFIG={
        "broker_url": os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379"),
        "result_backend": os.environ.get(
            "CELERY_RESULT_BACKEND", "redis://localhost:6379"
        ),
    }
)
app.secret_key = os.environ.get("SECRET_KEY", "mysecretkey")
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(__file__), "static")
celery = make_celery(app)

###############
## AWS Setup ##
###############

ENDPOINT_URL = os.environ.get("AWS_ENDPOINT_URL", "http://localhost:4566")
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID", "test")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "test")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
# print(ENDPOINT_URL)
# print(AWS_ACCESS_KEY_ID)
# print(AWS_SECRET_ACCESS_KEY)
# print(AWS_REGION)

dynamodb = boto3.resource(
    "dynamodb",
    endpoint_url=ENDPOINT_URL,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION,
)

s3 = boto3.resource(
    "s3",
    endpoint_url=ENDPOINT_URL,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION,
)


##################
## Celery Tasks ##
##################


@celery.task
def generate_captions(file_name: str, email: str, *args):
    file_hash = sha256()
    with open(file_name, "rb") as f:
        while True:
            data = f.read(65536)
            if not data:
                break
            file_hash.update(data)
    response = dynamodb.Table("captions").get_item(
        Key={"email": email, "file_hash": file_hash.hexdigest()}
    )
    # print(response)
    response = response.get("Item", [])
    # print(response if len(response) > 0 else "No response")
    if len(response) == 0 or response.get("file_hash", "") != file_hash.hexdigest():
        cmd = ["ccextractor", file_name, "-stdout"]
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        stdout, stderr = proc.communicate()
        # print(stderr)
        secure_name = secure_filename(file_name.split("/")[-1])
        data = {
            "index": [],
            "start": [],
            "end": [],
            "position": [],
            "text": [],
            "email": email,
            "file_hash": file_hash.hexdigest(),
            "file_name": secure_name,
        }
        if stdout:
            srt = pysrt.from_string(stdout)
            for sub in srt:
                dt = sub.__dict__
                for k, v in dt.items():
                    data[k].append(str(v))
        upload_file.delay(file_name, object_name=f"{email}/{secure_name}")
        load_captions_to_db.delay(data)
        return data
    return response

    # raise Exception("stderr")


@celery.task
def load_captions_to_db(data: list, *args):
    dynamodb.Table("captions").put_item(Item=data)


@celery.task
def upload_file(file_name, bucket="mybucket", object_name=None, *args):
    if object_name is None:
        object_name = os.path.basename(file_name)
    try:
        s3.meta.client.upload_file(file_name, bucket, object_name)
    except ClientError as e:
        logging.error(e)
        return False
    return True


##############################
## Login Required Decorator ##
##############################


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "email" not in request.cookies:
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return wrapper


######################
## Flask app routes ##
######################


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form["email"]
        table = dynamodb.Table("users")
        response = table.get_item(Key={"email": email})
        item = response.get("Item")
        if item:
            flash("Email already exists")
            return redirect(url_for("signup"))
        password = request.form["password"]
        pw_hash = generate_password_hash(password)
        table = dynamodb.Table("users")
        table.put_item(Item={"email": email, "password": pw_hash})
        path = os.path.join(app.config["UPLOAD_FOLDER"], email)
        os.mkdir(path)
        return redirect(url_for("login"))
    return render_template("signup.html", log=True)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.cookies.get("email"):
        return redirect(url_for("upload"))
    if request.method == "POST":
        try:
            email = request.form["email"]
            password = request.form["password"]
            table = dynamodb.Table("users")
            response = table.get_item(Key={"email": email})
            item = response.get("Item")
            if item:
                if check_password_hash(item["password"], password):
                    resp = make_response(redirect(url_for("upload")))
                    resp.set_cookie("email", email)
                    return resp
        except ClientError as e:
            flash(f"Incorrect email or password: {e}")
        return redirect(url_for("login"))
    return render_template("login.html", log=True)


@app.route("/logout")
@login_required
def logout():
    resp = make_response(redirect(url_for("login")))
    email = request.cookies.get("email")
    path = os.path.join(app.config["UPLOAD_FOLDER"], email)
    rmtree(path)
    os.mkdir(path)
    for key in request.cookies:
        resp.set_cookie(key, expires=0)
    return resp


@app.route("/", methods=["GET", "POST"])
@login_required
def upload():
    if request.method == "GET":
        return render_template("index.html", method="GET")
    else:
        f = request.files.getlist("file")
        email = request.cookies.get("email")
        secure_names = [secure_filename(x.filename) for x in f]
        upload_folder = app.config["UPLOAD_FOLDER"]
        paths = [
            f"{upload_folder}/{email}/{secure_name}" for secure_name in secure_names
        ]
        print(paths)
        # exts = [x.filename.split(".")[-1] for x in f]
        response = make_response(render_template("index.html", method="POST"))
        for i, file in enumerate(f):
            file.save(paths[i])
            task = generate_captions.delay(paths[i], email)
            response.set_cookie(file.filename, task.id)
        return response


@app.route("/search", methods=["GET", "POST"])
@login_required
def search():
    if request.method == "GET":
        email = request.cookies.get("email")
        uploads = os.listdir(
            os.path.join(os.path.dirname(__file__), "static", f"{email}")
        )
        return render_template("search.html", method="GET", checklist=uploads)
    else:
        search_term = request.form["q"]
        check_files = request.form.getlist("checklist")
        result_ids = [request.cookies.get(x) for x in check_files]
        results = [generate_captions.AsyncResult(result_id) for result_id in result_ids]
        data = [result.get() for result in results]
        email = request.cookies.get("email")
        returns = []
        for y in data:
            search_terms = []
            for i, x in enumerate(y["text"]):
                if search_term in x:
                    search_terms.append(
                        {"Start": y["start"][i], "End": y["end"][i], "Text": x}
                    )
            returns.append(search_terms)
        # print(returns)
        return render_template(
            "search.html",
            method="POST",
            data=returns,
            files=check_files,
            checklist=check_files,
        )


@app.route("/get-all-captions", methods=["GET"])
def get_captions():
    email = request.cookies.get("email")
    captions = dynamodb.Table("captions")
    response = captions.scan()
    returns = [item for item in response["Items"] if item["email"] == email]
    return render_template("captions.html", data=returns)


@app.route("/show-all-files", methods=["GET"])
def show_files():
    email = request.cookies.get("email")
    Bucket = s3.Bucket("mybucket")
    files = [obj.key for obj in Bucket.objects.all() if obj.key.startswith(email)]
    return files


if __name__ == "__main__":
    # app = create_app(celery=app.celery)
    # table = dynamodb.Table("captions")
    # table.delete()
    # table.wait_until_not_exists()
    # table = dynamodb.Table("users")
    # table.delete()
    # table.wait_until_not_exists()
    # print("Tables deleted")
    # create_table()
    # print(list(dynamodb.tables.all()))
    app.run(host="localhost", port=5000, debug=True)
