import subprocess
import pysrt

import os

# print(os.listdir(os.path.join(os.path.dirname(__file__), "stream_flask/static")))
# print(os.path.abspath("./stream_flask/static/big_buck_bunny_eac3_4.m2ts"))
cmd = ["ccextractor", "../big_buck_bunny_eac3_4.m2ts", "-stdout"]
proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
stdout, stderr = proc.communicate()
print("STDOUT:", stdout)
# print("STDERR:", stderr)
srt = pysrt.from_string(stdout)
data = []
for sub in srt:
    dt = sub.__dict__
    print(sub)
    dt["start"] = str(dt["start"])
    dt["end"] = str(dt["end"])
    data.append(dt)
# print(data)
# stdout, stderr = proc.communicate()

# srt = pysrt.open("../big_buck_bunny_eac3_4.srt")
# data = {
#     "index": [],
#     "start": [],
#     "end": [],
#     "position": [],
#     "text": [],
# }

# for sub in srt:
#     data["index"].append(sub.index)
#     data["start"].append(str(sub.start))
#     data["end"].append(str(sub.end))
#     data["position"].append(sub.position)
#     data["text"].append(sub.text)
# print(data)
