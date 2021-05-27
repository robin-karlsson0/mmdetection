import argparse
import json
import glob
import os.path as osp
import random

import mmcv


DEFAULT_AREA = 100

# Hardcoded 'category' --> 'category_id' conversion dictionaries
CATEGORY_A2D2_IDX = {
    'Pedestrian': 0,
    'Cyclist': 1,
    'MotorBiker': 2,
    'Car': 3,
    'VanSUV': 4,
    'Truck': 5,
    'Bus': 6,
    'UtilityVehicle': 7,
    'Trailer': 8,
    'CaravanTransporter': 9,
    'EmergencyVehicle': 10,
    'Motorcycle': 11,
    'Bicycle': 12,
    'Animal': 13,
}

CATEGORY_CITYSCAPES_IDX = {
    'Pedestrian': 24,
    'Cyclist': 25,
    'MotorBiker': 25,
    'Car': 26,
    'VanSUV': 26,
    'Truck': 27,
    'Bus': 28,
    'Motorcycle': 32,
    'Bicycle': 33,
    # Ignore
    'UtilityVehicle': None,
    'Trailer': None,
    'CaravanTransporter': None,
    'EmergencyVehicle': None,
    'Animal': None,
}

CATEGORIES_CITYSCAPES = [
        {"id": 24, "name": "person"},
        {"id": 25, "name": "rider"}, 
        {"id": 26, "name": "car"}, 
        {"id": 27, "name": "truck"},
        {"id": 28, "name": "bus"}, 
        {"id": 31, "name": "train"}, 
        {"id": 32, "name": "motorcycle"}, 
        {"id": 33, "name": "bicycle"}
    ]

def conv_category(category_str, target_dataset):
    '''Returns a 'category_id' corresponding to a A2D2 category string token.
    NOTE: Returns -1 for ignored categories.
    '''
    if target_dataset == 'a2d2':
        return CATEGORY_A2D2_IDX[category_str]
    elif target_dataset == 'cityscapes':
        return CATEGORY_CITYSCAPES_IDX[category_str]
    else:
        raise Exception(f'Invalid dataset conversion target ({target_dataset})')
    

def label2img_path(label_path):
    '''Returns the image path corresponding to a given label path.

    Leverages the A2D2 file structure naming conention.

    NOTE: The string could be converted in only two operations, but including
          explicit directory and filename syntax is more robust to unintended
          changes.
    '''
    # .../20180807_145028/label3D/cam_front_center/..._label3D_...000000091.json
    # .../20180807_145028/camera/cam_front_center/..._camera_...000000091.png
    img_path = label_path.replace('/label3D/', '/camera/')
    img_path = img_path.replace('_label3D_', '_camera_')
    img_path = img_path.replace('.json', '.png')
    return img_path


def collect_img_label_path_pairs(data_dir):
    '''Returns a list of paired image and label file paths.
    '''
    # List of all label file paths
    label_paths = glob.glob(f'{data_dir}/*/label3D/*/*.json')
    # List of all image file paths corresponding to found labels
    img_paths = [label2img_path(label_path) for label_path in label_paths]
    
    img_label_pairs = []
    for img_path, label_path in zip(img_paths, label_paths):
        pair = (img_path, label_path)
        img_label_pairs.append(pair)

    return img_label_pairs


def split_sample_list(sample_list, *split_Ns):
    '''Returns a list of splitted lists according to given split sample counts.
    '''
    idx0 = 0
    idx1 = 0
    split_lists = []
    for split_N in split_Ns:
        idx1 += split_N
        split_list = sample_list[idx0:idx1]
        split_lists.append(split_list)
        idx0 += split_N

    return split_lists


def gen_img_entry(img_path, img_idx, width=1920, height=1208):
    '''Returns a dict with keys and values constituting a JSON 'image entry'.
    '''
    img_entry = {
        'id': img_idx,
        'file_name': img_path,
        'width': width,
        'height': height
        # TODO: segm_file ???
    }

    return img_entry


def gen_ann_entry(ann_raw, ann_idx, img_idx, dataset_style='a2d2'):
    '''Returns an COCO annotation generated by a given A2D2 annotation entry.

    A2D2 bounding box annotation format same as COCO:
        '2d_bbox' --> [x_tl, y_tl, width, height]

    Args:
        ann_raw (dict): A2D2 annotation entry.
        ann_idx (int): Unique index of next annotation.
        img_idx (int): Unique index of image associated with the annotations.
        dataset_style (str): Label 'category_id' following either the
                             'a2d2' or 'cityscapes' format.
    Returns:
        ann_entry (dict): Annotation entry in the COCO format.
        ann_idx (int): Unique index of next annotation (incremented).
    '''
    # Obtain the 'category_id' corresponding to the A2D2 'class'
    category_id = conv_category(ann_raw['class'], dataset_style)
    # Skip invalid categories and return index without incrementing
    if category_id == None:
        return None, ann_idx
    # Create annotation entry and increment the annotation counter
    # [x_min, y_min, x_max, y_max] --> [x_corner, y_corner, width, height]
    a2d2_bbox = ann_raw['2d_bbox']
    coco_bbox = [
        a2d2_bbox[0],
        a2d2_bbox[1],
        a2d2_bbox[2] - a2d2_bbox[0],
        a2d2_bbox[3] - a2d2_bbox[1],
    ]
    ann_entry = {
        'id': ann_idx,
        'image_id': img_idx,
        'category_id': category_id,
        'bbox': coco_bbox,
        'area': DEFAULT_AREA,
        #'segmentation': ???
        'iscrowd': 0
    }
    ann_idx += 1

    return ann_entry, ann_idx


def gen_ann_entries(ann_path, ann_idx, img_idx, dataset_style):
    '''Returns a list of all valid annotations for one image and increments the
    annotation id counter.
    
    ann_entry_i: Dictionary defining an annotation.

    Args:
        ann_path (str): Path to annotation file associated with the image
                        associated with image index 'img_idx'.
        ann_idx (int): Unique index of next annotation.
        img_idx (int): Unique index of image associated with the annotations.
        dataset_style (str): Label 'category_id' following either the
                             'a2d2' or 'cityscapes' format.

    Returns:
        ann_entries (list): List of entries [ann_entry_1, ... , ann_entry_N]
        ann_idx (int): Unique index of next annotation (incremented).
    '''
    # Read A2D2 annotation file
    with open(ann_path) as f:
        anns = json.load(f)
    
    ann_entries = []

    for _, ann_raw in anns.items():
        ann_entry, ann_idx = gen_ann_entry(
            ann_raw, ann_idx, img_idx, dataset_style)

        # Skip invalid annotations (skipped category, etc.)
        if ann_entry:
            ann_entries.append(ann_entry)

    return ann_entries, ann_idx


def gen_cat_entries(dataset_style):
    '''Returns a new COCO format category dictionary according to dataset style. 
    '''
    if dataset_style == 'a2d2':
        raise NotImplementedError()
        #category_entries = CATEGORY_A2D2
    elif dataset_style == 'cityscapes':
        category_entries = CATEGORIES_CITYSCAPES
    else:
        raise Exception(f'Invalid dataset conversion target ({dataset_style})')
    # Remove ignored 'None' entries
    #clean_dict = {key:val for key, val in category_dict.items() if val != None}
    # Create list of reformated entry dicts
    #cat_entries = []
    #for key, val in clean_dict.items():
    #    cat_entries.append({'id': val, 'name': key})

    return category_entries


def write_json_file(
        cat_entries, img_entries, ann_entries, outdir_path, split, 
        pretty_json=True):
    """
    Args:
        List of dicts:
            category_entries: [{'id': 0, 'name': 'car'}, ...]
            img_entries: [{'id': 0, 'filename': 'path_to_image', ...}, ...]
            ann_entries: [{'id': 0, 'image_id': 0, 'category_id': 0, ...}, ...]
        outdir_path (str): Path to JSON file output directory.
        split (str): Identifying tag for data split.
        pretty_json (bool): If True, JSON file will have rows and indentation.
    """
    json_dict = {
        'categories': cat_entries,
        'images': img_entries,
        'annotations': ann_entries
    }

    if not osp.isdir(outdir_path):
            raise IOError(f'Specified JSON file output path invalid ({outdir_path})')
    output_file_path = osp.join(outdir_path, f'a2d2_{split}.json')

    with open(output_file_path, 'w') as f:
        if pretty_json:
            json_object = json.dumps(json_dict, indent=4)
            f.write(json_object)
        else:
            json.dump(json_dict, f)


def parse_args():
    parser = argparse.ArgumentParser(
        description='Convert A2D2 annotations to COCO format')
    parser.add_argument('a2d2_path', help='Path to dataset dir (i.e. a2d2/')
    parser.add_argument(
        '--pkg-dir', default='camera_lidar_semantic_bboxes', type=str)
    parser.add_argument(
        '--style', default='cityscapes', type=str, 
        help='Annotation style (\'a2d2\' or \'cityscapes\')'
    )
    parser.add_argument('-o', '--out-dir', help='Dir. of created JSON files')
    parser.add_argument(
        '--val', default=800, type=int, help='Number of validation samples')
    parser.add_argument(
        '--test', default=0, type=int, help='Number of testing samples')
    parser.add_argument(
        '--nproc', default=1, type=int, help='Number of process')
    parser.set_defaults(pretty_json=True)
    parser.add_argument(
        '--no-pretty',
        dest='pretty_json',
        action='store_false',
        help='Outputs a compact JSON file')
    args = parser.parse_args()
    return args


def main():
    """Program for converting Audi's A2D2 dataset to the COCO format.

    NOTE: The input argument path must be the ABSOLUTE PATH to the dataset
          - NOT the symbolically linked one (i.e. data/a2d2)!

    Segmentation label conversion:
        The A2D2 labels are instance segmentations (i.e. car_1, car_2, ...),
        while semantic segmentation requires categorical segmentations.

        The function 'convert_TYPE_trainids()' converts all instance
        segmentation to their corresponding categorical segmentation and saves
        them as new label image files.

        Conversion type options
            A2D2: Generates segmentations using inherent categories.
            Cityscapes: Generates segmentations according to the categories and
                        indexing (i.e. 'trainIds') as in Cityscapes.

    Directory restructuring:
        A2D2 files are not arranged in the required 'train/val/test' directory
        structure.

        The function 'restructure_a2d2_directory' creates a new compatible
        directory structure in the root directory, and fills it with symbolic
        links or file copies to the input and segmentation label images.

    Example usage:
        python tools/convert_datasets/a2d2.py path/to/camera_lidar_semantic
    """
    # Initialize variables
    args = parse_args()
    random.seed(12)
    a2d2_path = args.a2d2_path
    dataset_style = args.style
    out_dir = args.out_dir if args.out_dir else osp.join(a2d2_path, 'annotations')
    mmcv.mkdir_or_exist(out_dir)
    data_dir = osp.join(a2d2_path, args.pkg_dir)
    val_N = args.val
    test_N = args.test
    pretty_json = args.pretty_json

    # Make splits of all existing A2D2 (image, label) pair samples
    img_label_pairs = collect_img_label_path_pairs(data_dir)
    random.shuffle(img_label_pairs)

    tot_N = len(img_label_pairs)
    train_N = tot_N - val_N - test_N

    splits = split_sample_list(img_label_pairs, train_N, val_N, test_N)
    img_label_pairs_train = splits[0]
    img_label_pairs_val = splits[1]
    img_label_pairs_test = splits[2]
    
    splits = {
        'train': img_label_pairs_train,
        'val': img_label_pairs_val,
        'test': img_label_pairs_test
    }

    # Generate JSON file entires from each sample
    # - Each image has an unique ID 
    # - Each annotations has an unique ID and is associated to one image ID
    for name, split in splits.items():
        # Maintained counters for unique IDs for each split
        img_idx = 0
        ann_idx = 0
        img_entries = []
        ann_entries = []
        # Generate entries for each pair in the split
        for pair in split:
            img_path = pair[0]
            ann_path = pair[1]
            # Image JSON entry
            img_entry = gen_img_entry(img_path, img_idx)
            img_entries.append(img_entry)
            # Annotation JSON entries
            #   NOTE: img_idx is constant, ann_idx incremented
            # Generates all annotations for the image as a list of dicts
            # [ann_entry_1, ann_entry_2,  ... , ann_entry_N]
            ann_entries_, ann_idx = gen_ann_entries(
                ann_path, ann_idx, img_idx, dataset_style)
            ann_entries += ann_entries_

            # Increment index now that all annotations for the image are done
            img_idx += 1


        # Print JSON file
        cat_entries = gen_cat_entries(dataset_style)
        write_json_file(
            cat_entries, img_entries, ann_entries, out_dir, name, pretty_json)

    '''
    set_name = dict(
        train='a2d2_train.json',
        val='a2d2_val.json',
        test='a2d2_test.json')

    for split, json_name in set_name.items():
        print(f'Converting {split} into {json_name}')


        with mmcv.Timer(
                print_tmpl='It took {}s to convert Cityscapes annotation'):
            files = collect_files(
                osp.join(img_dir, split), osp.join(gt_dir, split))
            image_infos = collect_annotations(files, nproc=args.nproc)
            cvt_annotations(image_infos, osp.join(out_dir, json_name))
    '''

if __name__ == '__main__':
    main()