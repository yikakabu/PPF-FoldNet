from __future__ import print_function
from __future__ import division

from pathlib import Path
import argparse
import math
import numpy as np
import os.path as osp
import sys

ROOT_DIR = osp.abspath('../')
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

from utils import io as uio


# ---------------------------------------------------------------------------- #
# Fuse rgbd frames into fragments in 3DMatch
# - Use existing camera poses
# - Save colors & normals
# ---------------------------------------------------------------------------- #
def read_intrinsic(filepath, width, height):
    import open3d as o3d

    m = np.loadtxt(filepath, dtype=np.float32)
    intrinsic = o3d.camera.PinholeCameraIntrinsic(width, height, m[0, 0], m[1, 1], m[0, 2], m[1, 2])
    return intrinsic


def read_extrinsic(filepath):
    m = np.loadtxt(filepath, dtype=np.float32)
    if np.isnan(m).any():
        return None
    return m  # (4, 4)


def read_rgbd_image(cfg, color_file, depth_file, convert_rgb_to_intensity):
    import open3d as o3d
    if color_file is None:
        color_file = depth_file # to avoid "Unsupported image format."
        # rgbd_image = o3d.RGBDImage()
        # rgbd_image.depth = o3d.io.read_image(depth_file)
        # return rgbd_image
    color = o3d.io.read_image(color_file)
    depth = o3d.io.read_image(depth_file)
    rgbd_image = o3d.geometry.create_rgbd_image_from_color_and_depth(color, depth, cfg.depth_scale, cfg.depth_trunc,
                                                                     convert_rgb_to_intensity)
    return rgbd_image


def process_single_fragment(cfg, color_files, depth_files, frag_id, n_frags, intrinsic_path, out_folder):
    import open3d as o3d

    depth_only_flag = (len(color_files) == 0)
    n_frames = len(depth_files)
    intrinsic = read_intrinsic(intrinsic_path, cfg.width, cfg.height)
    if depth_only_flag:
        color_type = o3d.integration.TSDFVolumeColorType.__dict__['None']
    else:
        color_type = o3d.integration.TSDFVolumeColorType.__dict__['RGB8']
        
    volume = o3d.integration.ScalableTSDFVolume(voxel_length=cfg.tsdf_cubic_size / 512.0,
                                                sdf_trunc=0.04,
                                                color_type=color_type)

    sid = frag_id * cfg.frames_per_frag
    eid = min(sid + cfg.frames_per_frag, n_frames)
    pose_base2world = None
    pose_base2world_inv = None
    for fid in range(sid, eid):
        if not depth_only_flag:
            color_path = color_files[fid]
        else:
            color_path = None
        depth_path = depth_files[fid]
        pose_path = depth_path[:-10] + '.pose.txt'

        pose_cam2world = read_extrinsic(pose_path)
        if pose_cam2world is None:
            continue
        if fid == sid:  # Use as base frame
            pose_base2world = pose_cam2world
            pose_base2world_inv = np.linalg.inv(pose_base2world)
        if pose_base2world_inv is None:
            break
        # Relative camera pose
        pose_cam2world = np.matmul(pose_base2world_inv, pose_cam2world)

        rgbd = read_rgbd_image(cfg, color_path, depth_path, False)
        volume.integrate(rgbd, intrinsic, np.linalg.inv(pose_cam2world))
    if pose_base2world_inv is None:
        return

    pcloud = volume.extract_point_cloud()
    o3d.geometry.estimate_normals(pcloud)
    o3d.write_point_cloud(osp.join(out_folder, 'cloud_bin_{}.ply'.format(frag_id)), pcloud)

    np.save(osp.join(out_folder, 'cloud_bin_{}.pose.npy'.format(frag_id)), pose_base2world)


# ---------------------------------------------------------------------------- #
# Iterate Folders
# ---------------------------------------------------------------------------- #
def run_seq(cfg, scene, seq):
    print("    Start {}".format(seq))

    seq_folder = osp.join(cfg.dataset_root, scene, seq)
    color_names = uio.list_files(seq_folder, '*.color.png')
    color_paths = [osp.join(seq_folder, cf) for cf in color_names]
    depth_names = uio.list_files(seq_folder, '*.depth.png')
    depth_paths = [osp.join(seq_folder, df) for df in depth_names]
    # depth_paths = [osp.join(seq_folder, cf[:-10] + '.depth.png') for cf in depth_names]

    # n_frames = len(color_paths)
    n_frames = len(depth_paths)
    n_frags = int(math.ceil(float(n_frames) / cfg.frames_per_frag))

    out_folder = osp.join(cfg.out_root, scene, seq)
    uio.may_create_folder(out_folder)

    intrinsic_path = osp.join(cfg.dataset_root, scene, 'camera-intrinsics.txt')

    if cfg.threads > 1:
        from joblib import Parallel, delayed
        import multiprocessing

        Parallel(n_jobs=cfg.threads)(
            delayed(process_single_fragment)(cfg, color_paths, depth_paths, frag_id, n_frags, intrinsic_path, out_folder)
            for frag_id in range(n_frags))

    else:
        for frag_id in range(n_frags):
            process_single_fragment(cfg, color_paths, depth_paths, frag_id, n_frags, intrinsic_path, out_folder)

    print("    Finished {}".format(seq))


def run_scene(cfg, scene):
    print("  Start scene {} ".format(scene))

    scene_folder = osp.join(cfg.dataset_root, scene)
    seqs = uio.list_folders(scene_folder)
    print("  {} sequences".format(len(seqs)))
    for seq in seqs:
        run_seq(cfg, scene, seq)

    print("  Finished scene {} ".format(scene))


def run(cfg):
    print("Start making fragments")

    uio.may_create_folder(cfg.out_root)

    scenes = uio.list_folders(cfg.dataset_root, sort=False)
    print("{} scenes".format(len(scenes)))
    for scene in scenes:
        # if not scene.startswith('analysis'):
        #    continue
        run_scene(cfg, scene)

    print("Finished making fragments")


# ---------------------------------------------------------------------------- #
# Arguments
# ---------------------------------------------------------------------------- #
def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset_root', default='data/3DMatch/rgbd')
    parser.add_argument('--out_root', default='data/3DMatch/rgbd_fragments/')
    parser.add_argument('--depth_scale', type=float, default=1000.0)
    parser.add_argument('--depth_trunc', type=float, default=6.0)
    parser.add_argument('--frames_per_frag', type=int, default=50)
    parser.add_argument('--height', type=int, default=480)
    parser.add_argument('--threads', type=int, default=1)
    parser.add_argument('--tsdf_cubic_size', type=float, default=3.0)
    parser.add_argument('--width', type=int, default=640)

    return parser.parse_args()


if __name__ == '__main__':
    cfg = parse_args()
    run(cfg)
