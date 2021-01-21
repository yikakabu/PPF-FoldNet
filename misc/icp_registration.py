from open3d import *
import numpy as np
import copy
from input_preparation import rgbd_to_point_cloud, cal_local_normal


def draw_registration_result(source, target, transformation):
    source_temp = copy.deepcopy(source)
    target_temp = copy.deepcopy(target)
    source_temp.paint_uniform_color([1, 0.706, 0])
    target_temp.paint_uniform_color([0, 0.651, 0.929])
    source_temp.transform(transformation)
    draw_geometries([source_temp, target_temp])


if __name__ == "__main__":
    # source = read_point_cloud("../../TestData/ICP/cloud_bin_0.pcd")
    # target = read_point_cloud("../../TestData/ICP/cloud_bin_1.pcd")
    data_dir = "data/train/sun3d-harvard_c11-hv_c11_2/seq-01-train"
    source = rgbd_to_point_cloud(data_dir, "000002")
    target = rgbd_to_point_cloud(data_dir, "000003")
    cal_local_normal(source)
    cal_local_normal(target)
    threshold = 0.02
   # threshold is the  – Maximum correspondence points pair distance

    # trans_init = np.asarray(
    #             [[0.862, 0.011, -0.507,  0.5],
    #             [-0.139, 0.967, -0.215,  0.7],
    #             [0.487, 0.255,  0.835, -1.4],
    #             [0.0, 0.0, 0.0, 1.0]])
    trans_init = np.asarray(
        [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    )
    draw_registration_result(source, target, trans_init)
    print("Initial alignment")
    evaluation = evaluate_registration(source, target, threshold, trans_init)
    print(evaluation)

    print("Apply point-to-point ICP")
    reg_p2p = registration_icp(source, target, threshold, trans_init, TransformationEstimationPointToPoint())
    print(reg_p2p)
    print("Transformation is:")
    print(reg_p2p.transformation)
    print("")
    draw_registration_result(source, target, reg_p2p.transformation)

    print("Apply point-to-plane ICP")
    reg_p2l = registration_icp(source, target, threshold, trans_init, TransformationEstimationPointToPlane())
    print(reg_p2l)
    print("Transformation is:")
    print(reg_p2l.transformation)
    print("")
    draw_registration_result(source, target, reg_p2l.transformation)
