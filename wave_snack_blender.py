"""
Wave Snack - stand-up pouch generator for Blender (3.x / 4.x)
วิธีใช้: เปิด Blender > แท็บ Scripting > Open ไฟล์นี้ > กด Run Script
ได้ซองขนม 2 ห่อ แล้วส่งออก OBJ ให้อัตโนมัติ
"""
import math
import os
import shutil

import bpy
import bmesh
import numpy as np

# ============ ตั้งค่าตรงนี้ ============
BASE_DIR = r"C:\Users\nongm\OneDrive\เดสก์ท็อป\WaveSnack"

BAGS = [
    {
        "name": "WaveSnack_Squid",
        "texture": os.path.join(BASE_DIR, "Wave Snack ข้าวเกรียบรสปลาหมึกย่าง_แบบใหม่-01.jpg"),
        "back_color": (0.60, 0.03, 0.05, 1.0),   # แดง (ด้านหลัง/ข้าง/ก้นซอง)
        "x_offset": -0.10,
        "front_crop": 0.14,   # ตัดพื้นว่างล่างลายด้านหน้า (ยิ่งมาก ลายยิ่งถูกดึงลงถึงก้น)
        "back_crop": 0.18,    # ตัดพื้นว่างล่างลายด้านหลัง
    },
    {
        "name": "WaveSnack_Tomato",
        "texture": os.path.join(BASE_DIR, "Wave Snack ข้าวเกรียบรสมะเขือเทศ_แบบใหม่-01.jpg"),
        "back_color": (0.45, 0.04, 0.40, 1.0),   # ม่วง
        "x_offset": 0.10,
        "front_crop": 0.14,
        "back_crop": 0.18,
        "layout_ref": True,   # ซองอ้างอิง: ซองอื่นใช้กรอบลายเดียวกับซองนี้
    },
]

EXPORT_DIR = os.path.join(BASE_DIR, "export")

# ขนาดซอง (เมตร)
W, H, D = 0.148, 0.20, 0.055     # กว้าง, สูง, ความป่องตรงกลาง
T = 0.0008                      # ครึ่งหนึ่งของความหนาฟิล์ม
SEAL = 0.018                    # ความสูงรอยซีลบน
NX, NY = 48, 72                 # ความละเอียดตาราง

# ไฟล์ดีไซน์เป็นภาพกางหน้า+หลัง (มีขอบขาวรอบ)
AUTO_CROP = True        # ตัดขอบขาวออกอัตโนมัติ
SPLIT = 0.5             # ตำแหน่งแบ่งหน้า/หลังในกรอบลาย (0-1) ถ้ารอยแบ่งไม่ตรง ให้ปรับเลขนี้
FRONT_IS_LEFT = True    # ด้านหน้าซองอยู่ซ้ายของภาพ (ถ้าสลับหน้า/หลัง ให้ตั้งเป็น False)
ROTATE_ART = "CW"       # หมุนลายให้ตั้งตรง: "CW" = หมุนตามเข็ม 90°, "CCW" = ทวนเข็ม 90°, None = ไม่หมุน
SHARE_LAYOUT = True     # ให้ทุกซองใช้กรอบลายเดียวกับซองอ้างอิง (layout_ref) -> ความยาวลายเท่ากันเป๊ะ
ART_BOTTOM_CROP = 0.14  # ตัดส่วนล่างของลายที่เป็นพื้นว่าง/ก้นซองออก (0-1) แล้วขยายลายลงมาถึงก้นซอง
                        # ถ้าลายยังไม่ถึงก้น เพิ่มค่านี้ / ถ้าลายล้นหาย ลดค่านี้
STAND_UP_ROTATION_X = 90  # องศาที่หมุนซองรอบแกน X ให้ตั้งตรง (Rotation X ใน Blender)
AUTO_WIDTH = False      # ปิดไว้: ใช้สัดส่วนซองตามรูปถ่าย (กว้าง:สูง ≈ 0.74) ถ้าลายเพี้ยนค่อยเปิด
# =====================================


def smoothstep(a, b, x):
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


# --- ทรงโค้งด้านข้างตามรูปถ่าย ---
BOTTOM_NARROW = 0.86    # ก้นซองแคบลงเหลือกี่เท่าของความกว้างสูงสุด
BOTTOM_ZONE = 0.50      # ช่วงความสูงจากก้นที่ค่อยๆ แคบลง (0-1)
BARREL = 0.018          # ความโค้งป่องของข้างซองช่วงกลางตัว
TOP_ROUND = 0.05        # ความโค้งมนของมุมบน


def width_scale(y):
    """ตัวคูณความกว้างที่ความสูง y -> ขอบข้างซองโค้งตามรูปถ่าย"""
    yn = y / H
    t = min(1.0, yn / BOTTOM_ZONE)
    sc = BOTTOM_NARROW + (1 - BOTTOM_NARROW) * math.sin(t * math.pi / 2)
    sc += BARREL * math.sin(math.pi * yn)
    rc = 0.06
    if yn > 1 - rc:
        d = (yn - (1 - rc)) / rc
        sc *= 1 - TOP_ROUND * d * d
    return sc


def bulge(x, y):
    """ความป่องของผิวซองที่ตำแหน่ง (x, y)"""
    u = (2 * x) / W
    prof = max(0.0, 1 - u * u) ** 0.6
    yn = y / H
    seal_n = SEAL / H
    g = 1.0 - smoothstep(0.40, 1.0 - seal_n - 0.04, yn)
    z = (D / 2) * prof * g
    # รอยย่นเป็นซี่ๆ ตรงรอยซีลบน
    if y > H - SEAL:
        z += 0.0004 * math.sin(y * 900)
    return z


def build_pouch_data(front_uv, back_uv, front_crop=0.14, back_crop=0.18):
    """คืนค่า verts, faces, face_mat, face_uvs (เป็น Python ล้วน)"""
    verts, faces, mats, uvs = [], [], [], []
    stride = NX + 1

    def xs(i):
        return -W / 2 + W * i / NX

    def ys(j):
        return H * j / NY

    # ด้านหน้า
    for j in range(NY + 1):
        for i in range(NX + 1):
            x, y = xs(i), ys(j)
            verts.append((x * width_scale(y), y, T + bulge(x, y)))
    back_off = len(verts)
    # ด้านหลัง
    for j in range(NY + 1):
        for i in range(NX + 1):
            x, y = xs(i), ys(j)
            verts.append((x * width_scale(y), y, -(T + bulge(x, y))))

    def F(i, j):
        return j * stride + i

    def B(i, j):
        return back_off + j * stride + i

    u0, v0, u1, v1 = front_uv
    bu0, bv0, bu1, bv1 = back_uv

    def panel_uv(rect, px, py):
        """px,py = ตำแหน่งบนซอง (0-1, ขวา/บน) -> พิกัดภาพ โดยหมุนลายตาม ROTATE_ART"""
        s0, t0, s1, t1 = rect
        if ROTATE_ART == "CW":
            return (s1 - (s1 - s0) * py, t0 + (t1 - t0) * px)
        if ROTATE_ART == "CCW":
            return (s0 + (s1 - s0) * py, t1 - (t1 - t0) * px)
        return (s0 + (s1 - s0) * px, t0 + (t1 - t0) * py)

    def uv_front(i, j):
        return panel_uv(front_uv, i / NX, front_crop + (1 - front_crop) * (j / NY))  # ดึงลายลงถึงก้น

    def uv_back(i, j):  # ด้านหลัง: หมุนลาย 180° (แก้ซองกลับหัว)
        return panel_uv(back_uv, i / NX, (1 - back_crop) * (1 - j / NY))  # หลัง: ลายกลับด้าน ก้นซองอยู่ท้ายลาย

    for j in range(NY):
        for i in range(NX):
            faces.append((F(i, j), F(i + 1, j), F(i + 1, j + 1), F(i, j + 1)))
            mats.append(0)
            uvs.append([uv_front(i, j), uv_front(i + 1, j),
                        uv_front(i + 1, j + 1), uv_front(i, j + 1)])
            faces.append((B(i, j), B(i, j + 1), B(i + 1, j + 1), B(i + 1, j)))
            mats.append(0)
            uvs.append([uv_back(i, j), uv_back(i, j + 1),
                        uv_back(i + 1, j + 1), uv_back(i + 1, j)])

    # แถบปิดข้าง ซ้าย/ขวา/บน
    for j in range(NY):
        for i in (0, NX):
            faces.append((F(i, j), F(i, j + 1), B(i, j + 1), B(i, j)))
            mats.append(1)
            uvs.append([(0, 0)] * 4)
    for i in range(NX):
        faces.append((F(i, NY), B(i, NY), B(i + 1, NY), F(i + 1, NY)))
        mats.append(1)
        uvs.append([(0, 0)] * 4)

    # ก้นซอง: พัดสามเหลี่ยมจากจุดกลาง
    center = len(verts)
    verts.append((0.0, 0.0, 0.0))
    loop = [F(i, 0) for i in range(NX + 1)] + [B(i, 0) for i in range(NX, -1, -1)]
    for k in range(len(loop)):
        a, b = loop[k], loop[(k + 1) % len(loop)]
        if a == b:
            continue
        faces.append((center, a, b))
        mats.append(1)
        uvs.append([(0, 0)] * 3)

    return verts, faces, mats, uvs


# ---------- ส่วนที่ใช้ Blender ----------

def make_front_material(name, image_path):
    mat = bpy.data.materials.new(name + "_front")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(image_path)
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    for key, val in (("Roughness", 0.18), ("Metallic", 0.25),
                     ("Coat Weight", 0.5), ("Clearcoat", 0.5)):
        if key in bsdf.inputs:
            bsdf.inputs[key].default_value = val
    return mat


def make_solid_material(name, color):
    mat = bpy.data.materials.new(name + "_back")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    for key, val in (("Roughness", 0.25), ("Metallic", 0.25)):
        if key in bsdf.inputs:
            bsdf.inputs[key].default_value = val
    return mat


_REF = {}


def detect_art_rects(image_path, is_ref=False):
    """หากรอบลาย (ตัดขอบขาว) แล้วแบ่งเป็นหน้า/หลัง คืนค่า front_uv, back_uv, อัตราส่วน กว้าง/สูง ของหน้าซอง"""
    img = bpy.data.images.load(image_path, check_existing=True)
    w, h = img.size
    if SHARE_LAYOUT and not is_ref and _REF:
        if _REF["size"] == (w, h):
            print("ใช้กรอบลายเดียวกับซองอ้างอิง:", os.path.basename(image_path))
            return _REF["result"]
        print("เตือน: ขนาดไฟล์ไม่เท่าซองอ้างอิง ใช้กรอบลายของไฟล์นี้เอง:", os.path.basename(image_path))
    x0, y0, x1, y1 = 0.0, 0.0, 1.0, 1.0
    if AUTO_CROP:
        arr = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(arr)
        arr = arr.reshape(h, w, 4)[::4, ::4, :3]
        nonwhite = arr.min(axis=2) < 0.92
        cols = np.where(nonwhite.mean(axis=0) > 0.03)[0]
        rows = np.where(nonwhite.mean(axis=1) > 0.03)[0]
        sh, sw = nonwhite.shape
        if len(cols) and len(rows):
            x0, x1 = cols[0] / sw, (cols[-1] + 1) / sw
            y0, y1 = rows[0] / sh, (rows[-1] + 1) / sh
    xm = x0 + (x1 - x0) * SPLIT
    left = (x0, y0, xm, y1)
    right = (xm, y0, x1, y1)
    front, back = (left, right) if FRONT_IS_LEFT else (right, left)
    pw = (front[2] - front[0]) * w   # ความกว้างลายในภาพ (พิกเซล)
    ph = (front[3] - front[1]) * h   # ความสูงลายในภาพ (พิกเซล)
    aspect = (ph / max(1.0, pw)) if ROTATE_ART else (pw / max(1.0, ph))
    print("กรอบลาย:", (x0, y0, x1, y1), "สัดส่วนหน้าซอง:", round(aspect, 3))
    result = (front, back, aspect)
    if is_ref:
        _REF.update(size=(w, h), result=result)
    return result


def create_bag(cfg):
    global W
    front_uv, back_uv, aspect = detect_art_rects(cfg["texture"])
    W = max(0.10, min(0.18, H * aspect)) if AUTO_WIDTH else W
    verts, faces, mats, uvs = build_pouch_data(front_uv, back_uv, cfg.get("front_crop", ART_BOTTOM_CROP), cfg.get("back_crop", ART_BOTTOM_CROP))
    mesh = bpy.data.meshes.new(cfg["name"])
    bm = bmesh.new()
    bv = [bm.verts.new(v) for v in verts]
    uv_layer = bm.loops.layers.uv.new("UVMap")
    for f, m, uv in zip(faces, mats, uvs):
        try:
            face = bm.faces.new([bv[i] for i in f])
        except ValueError:
            continue
        face.material_index = m
        for loop, (u, v) in zip(face.loops, uv):
            loop[uv_layer].uv = (u, v)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(cfg["name"], mesh)
    bpy.context.collection.objects.link(obj)
    obj.location = (cfg["x_offset"], 0, 0)
    obj.rotation_euler = (math.radians(STAND_UP_ROTATION_X), 0, 0)   # ตั้งซองตรง (Rotation X = 90°)

    # คัดลอกไฟล์ดีไซน์ไปชื่อ ASCII กันปัญหาชื่อไฟล์ไทยใน OBJ/MTL
    os.makedirs(EXPORT_DIR, exist_ok=True)
    ascii_tex = os.path.join(EXPORT_DIR, cfg["name"] + "_front.jpg")
    shutil.copy(cfg["texture"], ascii_tex)

    mesh.materials.append(make_front_material(cfg["name"], ascii_tex))
    mesh.materials.append(make_solid_material(cfg["name"], cfg["back_color"]))
    for p in mesh.polygons:
        p.use_smooth = True
    return obj


def export_obj(path, objects):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objects:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    if hasattr(bpy.ops.wm, "obj_export"):          # Blender 3.2+ / 4.x
        bpy.ops.wm.obj_export(filepath=path, export_selected_objects=True,
                              export_uv=True, export_materials=True,
                              path_mode="COPY")
    else:                                           # Blender 2.8 - 3.1
        bpy.ops.export_scene.obj(filepath=path, use_selection=True,
                                 use_uvs=True, use_materials=True,
                                 path_mode="COPY")


def clean_scene():
    for o in list(bpy.data.objects):
        if o.name == "Cube" or o.name.startswith("WaveSnack_"):
            bpy.data.objects.remove(o, do_unlink=True)


def main():
    clean_scene()
    for cfg in BAGS:
        if not os.path.exists(cfg["texture"]):
            raise FileNotFoundError("ไม่พบไฟล์ดีไซน์: " + cfg["texture"])

    _REF.clear()
    for cfg in BAGS:                       # หากรอบลายของซองอ้างอิงก่อน
        if cfg.get("layout_ref"):
            detect_art_rects(cfg["texture"], is_ref=True)

    bags = [create_bag(cfg) for cfg in BAGS]

    for b in bags:                                  # ส่งออกแยกทีละห่อ
        saved = b.location.copy()
        b.location = (0, 0, 0)
        export_obj(os.path.join(EXPORT_DIR, b.name + ".obj"), [b])
        b.location = saved
    export_obj(os.path.join(EXPORT_DIR, "WaveSnack_Both.obj"), bags)  # รวมสองห่อ
    print("เสร็จแล้ว! ไฟล์ OBJ อยู่ที่:", EXPORT_DIR)


if __name__ == "__main__":
    main()
