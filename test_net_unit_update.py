# --------------------------------------------------------
# Tensorflow Faster R-CNN
# Licensed under The MIT License [see LICENSE for details]
# Written by Jiasen Lu, Jianwei Yang, based on code from Ross Girshick
# --------------------------------------------------------
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import _init_paths
import os
import sys
import numpy as np
import argparse
import pprint
import pdb
import time
import cv2
import torch
import torchvision
from torch.autograd import Variable
import torch.nn as nn
import torch.optim as optim
import pickle
from PIL import Image
import torchvision.transforms.functional as TF
from roi_data_layer.roidb import combined_roidb
from roi_data_layer.roibatchLoader import roibatchLoader
from model.utils.config import cfg, cfg_from_file, cfg_from_list, get_output_dir
from model.rpn.bbox_transform import clip_boxes
# from model.nms.nms_wrapper import nms
from model.roi_layers import nms
from model.rpn.bbox_transform import bbox_transform_inv
from model.utils.net_utils import save_net, load_net, vis_detections

import sys
sys.path.insert(0, './lib/model/unit')
from model.unit.utils import get_config, pytorch03_to_pytorch04
from model.unit.trainer import MUNIT_Trainer, UNIT_Trainer
from model.unit.networks_test import VAEGenA, VAEGenB
import torchvision.utils as vutils
from PIL import Image

from copy import deepcopy

from model.faster_rcnn.vgg16 import vgg16
from model.faster_rcnn.resnet_dual import resnet

import pdb

try:
    xrange          # Python 2
except NameError:
    xrange = range  # Python 3


def parse_args():
  """
  Parse input arguments
  """
  parser = argparse.ArgumentParser(description='Train a Fast R-CNN network')
  parser.add_argument('--dataset', dest='dataset',
                      help='training dataset',
                      default='pascal_voc', type=str)
  parser.add_argument('--cfg', dest='cfg_file',
                      help='optional config file',
                      default='cfgs/vgg16.yml', type=str)
  parser.add_argument('--net', dest='net',
                      help='vgg16, res50, res101, res152',
                      default='res101', type=str)
  parser.add_argument('--set', dest='set_cfgs',
                      help='set config keys', default=None,
                      nargs=argparse.REMAINDER)
  parser.add_argument('--load_dir', dest='load_dir',
                      help='directory to load models', default="models",
                      type=str)
  parser.add_argument('--cuda', dest='cuda',
                      help='whether use CUDA',
                      action='store_true')
  parser.add_argument('--ls', dest='large_scale',
                      help='whether use large imag scale',
                      action='store_true')
  parser.add_argument('--mGPUs', dest='mGPUs',
                      help='whether use multiple GPUs',
                      action='store_true')
  parser.add_argument('--cag', dest='class_agnostic',
                      help='whether perform class_agnostic bbox regression',
                      action='store_true')
  parser.add_argument('--parallel_type', dest='parallel_type',
                      help='which part of model to parallel, 0: all, 1: model before roi pooling',
                      default=0, type=int)
  parser.add_argument('--checksession', dest='checksession',
                      help='checksession to load model',
                      default=1, type=int)
  parser.add_argument('--checkepoch', dest='checkepoch',
                      help='checkepoch to load network',
                      default=1, type=int)
  parser.add_argument('--checkpoint', dest='checkpoint',
                      help='checkpoint to load network',
                      default=10021, type=int)
  parser.add_argument('--vis', dest='vis',
                      help='visualization mode',
                      action='store_true')
  parser.add_argument('--use_tfb', dest='use_tfboard',
                      help='whether use tensorboard',
                      action='store_true')
                      
  parser.add_argument('--config', default='./lib/model/unit/configs/unit_rgb2thermal_folder.yaml', type=str, help="net configuration")
  parser.add_argument('--input', default=None, type=str, help="input image path")
  parser.add_argument('--output_folder', default='.', type=str, help="output image path")
  parser.add_argument('--checkpoint_unit', default='./lib/model/unit/models/rgb2thermal.pt', type=str, help="checkpoint of autoencoders")
  parser.add_argument('--style', type=str, default='', help="style image path")
  parser.add_argument('--a2b', type=int, default=0, help="1 for a2b and others for b2a")
  parser.add_argument('--seed', type=int, default=10, help="random seed")
  parser.add_argument('--num_style',type=int, default=10, help="number of styles to sample")
  parser.add_argument('--synchronized', action='store_true', help="whether use synchronized style code or not")
  parser.add_argument('--output_only', action='store_true', help="whether use synchronized style code or not")
  parser.add_argument('--output_path', type=str, default='.', help="path for logs, checkpoints, and VGG model weight")
  parser.add_argument('--trainer', type=str, default='UNIT', help="MUNIT|UNIT")


  args = parser.parse_args()
  return args

lr = cfg.TRAIN.LEARNING_RATE
momentum = cfg.TRAIN.MOMENTUM
weight_decay = cfg.TRAIN.WEIGHT_DECAY

# def get_unit_models(opts):

#     config = get_config(opts.config)
#     opts.num_style = 1 if opts.style != '' else opts.num_style
#     config['vgg_model_path'] = opts.output_path
#     trainer = UNIT_Trainer(config)
#     try:
#         state_dict = torch.load(opts.checkpoint_unit)
#         trainer.gen_a.load_state_dict(state_dict['a'])
#         trainer.gen_b.load_state_dict(state_dict['b'])
#     except:
#         state_dict = pytorch03_to_pytorch04(torch.load(opts.checkpoint_unit))
#         trainer.gen_a.load_state_dict(state_dict['a'])
#         trainer.gen_b.load_state_dict(state_dict['b'])
#     trainer.cuda()
#     trainer.eval()
#     encode = trainer.gen_a.encode if opts.a2b else trainer.gen_b.encode # encode function
#     style_encode = trainer.gen_b.encode if opts.a2b else trainer.gen_a.encode # encode function
#     decode = trainer.gen_b.decode if opts.a2b else trainer.gen_a.decode # decode function

#     return encode, decode


class Resize_GPU(nn.Module):
    def __init__(self, h, w):
        super(Resize_GPU, self).__init__()
        self.op =  nn.AdaptiveAvgPool2d((h,w))
    def forward(self, x):
        x = self.op(x)
        return x

lr = cfg.TRAIN.LEARNING_RATE
momentum = cfg.TRAIN.MOMENTUM
weight_decay = cfg.TRAIN.WEIGHT_DECAY

if __name__ == '__main__':

  args = parse_args()

  print('Called with args:')
  print(args)

  if torch.cuda.is_available() and not args.cuda:
    print("WARNING: You have a CUDA device, so you should probably run with --cuda")

  np.random.seed(cfg.RNG_SEED)
  if args.dataset == "pascal_voc":
      args.imdb_name = "voc_2007_trainval"
      args.imdbval_name = "voc_2007_test"
      args.set_cfgs = ['ANCHOR_SCALES', '[8, 16, 32]', 'ANCHOR_RATIOS', '[0.5,1,2]']
  elif args.dataset == "pascal_voc_0712":
      args.imdb_name = "voc_2007_trainval+voc_2012_trainval"
      args.imdbval_name = "voc_2007_test"
      args.set_cfgs = ['ANCHOR_SCALES', '[8, 16, 32]', 'ANCHOR_RATIOS', '[0.5,1,2]']
  elif args.dataset == "coco":
      args.imdb_name = "coco_2014_train+coco_2014_valminusminival"
      args.imdbval_name = "coco_2014_minival"
      args.set_cfgs = ['ANCHOR_SCALES', '[4, 8, 16, 32]', 'ANCHOR_RATIOS', '[0.5,1,2]']
  elif args.dataset == "imagenet":
      args.imdb_name = "imagenet_train"
      args.imdbval_name = "imagenet_val"
      args.set_cfgs = ['ANCHOR_SCALES', '[8, 16, 32]', 'ANCHOR_RATIOS', '[0.5,1,2]']
  elif args.dataset == "vg":
      args.imdb_name = "vg_150-50-50_minitrain"
      args.imdbval_name = "vg_150-50-50_minival"
      args.set_cfgs = ['ANCHOR_SCALES', '[4, 8, 16, 32]', 'ANCHOR_RATIOS', '[0.5,1,2]']

  args.cfg_file = "cfgs/{}_ls.yml".format(args.net) if args.large_scale else "cfgs/{}.yml".format(args.net)

  if args.cfg_file is not None:
    cfg_from_file(args.cfg_file)
  if args.set_cfgs is not None:
    cfg_from_list(args.set_cfgs)

  # print('Using config:')
  # pprint.pprint(cfg)

  cfg.TRAIN.USE_FLIPPED = False
  imdb, roidb, ratio_list, ratio_index = combined_roidb(args.imdbval_name, False)
  imdb.competition_mode(on=True)

  print('{:d} roidb entries'.format(len(roidb)))

  input_dir = args.load_dir + "/" + args.net + "/" + args.dataset
  if not os.path.exists(input_dir):
    raise Exception('There is no input directory for loading network from ' + input_dir)
  load_name = os.path.join(input_dir,
    'faster_rcnn_{}_{}_{}.pth'.format(args.checksession, args.checkepoch, args.checkpoint))
  # load_name_gen_a = os.path.join(input_dir,
  #   'gen_a_{}_{}_{}.pth'.format(args.checksession, args.checkepoch, args.checkpoint))
  # load_name_gen_b = os.path.join(input_dir,
  #   'gen_b_{}_{}_{}.pth'.format(args.checksession, args.checkepoch, args.checkpoint))

  # initilize the network here.

  if args.net in ['res101_unit_update', 'res101_unit_update_coco', 'res101_unit_update_coco_final']:
    fasterRCNN = resnet(imdb.classes, 101, pretrained=False, class_agnostic=args.class_agnostic)
  else:
    print("network is not defined")
    pdb.set_trace()

  fasterRCNN.create_architecture()
  config = get_config(args.config)

  # gen_a = VAEGenA(config['input_dim_a'], config['gen'])
  # gen_b = VAEGenB(config['input_dim_b'], config['gen'])
  
  # checkpoint_a = torch.load(load_name_gen_a)
  # checkpoint_b = torch.load(load_name_gen_b)


  # gen_a.load_state_dict(checkpoint_a['model'])
  # gen_b.load_state_dict(checkpoint_b['model'])

  # print('n\n\n\n\****Loaded GAN weights****\n')
  
  # gen_a = gen_a.cuda()
  # gen_b = gen_b.cuda()

  print("load checkpoint %s" % (load_name))
  checkpoint = torch.load(load_name)

  fasterRCNN.load_state_dict(checkpoint['model'])
  if 'pooling_mode' in checkpoint.keys():
    cfg.POOLING_MODE = checkpoint['pooling_mode']


  print('load model successfully!')


  if args.mGPUs:
    print('data parallel')
    fasterRCNN = nn.DataParallel(fasterRCNN)

  # initialize the tensor holder here.
  im_data = torch.FloatTensor(1)
  im_info = torch.FloatTensor(1)
  num_boxes = torch.LongTensor(1)
  gt_boxes = torch.FloatTensor(1)

  # ship to cuda
  if args.cuda:
    im_data = im_data.cuda()
    im_info = im_info.cuda()
    num_boxes = num_boxes.cuda()
    gt_boxes = gt_boxes.cuda()

  # make variable
  im_data = Variable(im_data)
  im_info = Variable(im_info)
  num_boxes = Variable(num_boxes)
  gt_boxes = Variable(gt_boxes)

  if args.cuda:
    cfg.CUDA = True

  if args.cuda:
    fasterRCNN.cuda()

  start = time.time()
  max_per_image = 100

  vis = args.vis

  if vis:
    thresh = 0.05
  else:
    thresh = 0.0

  save_name = 'faster_rcnn_10'
  num_images = len(imdb.image_index)
  all_boxes = [[[] for _ in xrange(num_images)]
               for _ in xrange(imdb.num_classes)]

  output_dir = get_output_dir(imdb, save_name)
  dataset = roibatchLoader(roidb,imdb, ratio_list, ratio_index, 1, \
                        imdb.num_classes, training=False, normalize = False)
  dataloader = torch.utils.data.DataLoader(dataset, batch_size=1,
                            shuffle=False, num_workers=0,
                            pin_memory=True)

  data_iter = iter(dataloader)

  _t = {'im_detect': time.time(), 'misc': time.time()}
  det_file = os.path.join(output_dir, 'detections.pkl')

  # if args.use_tfboard:
  #   from tensorboardX import SummaryWriter
  #   logger = SummaryWriter(f'logs/{cfg.EXP_DIR}_test/')

  fasterRCNN.eval()
  empty_array = np.transpose(np.array([[],[],[],[],[]]), (1,0))
  for i in range(num_images):

      data = next(data_iter)
      with torch.no_grad():
        im_data.resize_(data[0].size()).copy_(data[0])
        im_info.resize_(data[1].size()).copy_(data[1])
        gt_boxes.resize_(data[2].size()).copy_(data[2])
        num_boxes.resize_(data[3].size()).copy_(data[3])

      im_shape = im_data.size()
      nw_resize = Resize_GPU(im_shape[2], im_shape[3])


      # content, _ = gen_b(im_data)
      # outputs = gen_a(content)
      # im_data_1 = (outputs + 1) / 2.
      # im_data_1 = nw_resize(im_data_1)

      rgb_path = data[4][0]
      # thermal_path = rgb_path.replace('RGB_Images','JPEGImages')
      # thermal_path = thermal_path.replace('.jpg','.jpeg')

      img_rgb = np.array(Image.open(rgb_path))
      img_rgb = torchvision.transforms.ToTensor()(img_rgb)
      img_rgb.unsqueeze_(0)
      img_rgb = img_rgb.cuda()

      # img_thermal = np.array(Image.open(thermal_path))
      # img_thermal = np.stack((img_thermal,)*3, axis=-1)
      # img_thermal = torchvision.transforms.ToTensor()(img_thermal)
      # img_thermal.unsqueeze_(0)
      # img_thermal = img_thermal.cuda()      

      det_tic = time.time()
      rois, cls_prob, bbox_pred, \
      rpn_loss_cls, rpn_loss_box, \
      RCNN_loss_cls, RCNN_loss_bbox, \
      rois_label = fasterRCNN(img_rgb, im_data, im_info, gt_boxes, num_boxes)

      scores = cls_prob.data
      boxes = rois.data[:, :, 1:5]

      if cfg.TEST.BBOX_REG:
          # Apply bounding-box regression deltas
          box_deltas = bbox_pred.data
          if cfg.TRAIN.BBOX_NORMALIZE_TARGETS_PRECOMPUTED:
          # Optionally normalize targets by a precomputed mean and stdev
            if args.class_agnostic:
                box_deltas = box_deltas.view(-1, 4) * torch.FloatTensor(cfg.TRAIN.BBOX_NORMALIZE_STDS).cuda() \
                           + torch.FloatTensor(cfg.TRAIN.BBOX_NORMALIZE_MEANS).cuda()
                box_deltas = box_deltas.view(1, -1, 4)
            else:
                box_deltas = box_deltas.view(-1, 4) * torch.FloatTensor(cfg.TRAIN.BBOX_NORMALIZE_STDS).cuda() \
                           + torch.FloatTensor(cfg.TRAIN.BBOX_NORMALIZE_MEANS).cuda()
                box_deltas = box_deltas.view(1, -1, 4 * len(imdb.classes))

          pred_boxes = bbox_transform_inv(boxes, box_deltas, 1)
          pred_boxes = clip_boxes(pred_boxes, im_info.data, 1)
      else:
          # Simply repeat the boxes, once for each class
          pred_boxes = np.tile(boxes, (1, scores.shape[1]))

      pred_boxes /= data[1][0][2].item()

      scores = scores.squeeze()
      pred_boxes = pred_boxes.squeeze()
      det_toc = time.time()
      detect_time = det_toc - det_tic
      misc_tic = time.time()
      if vis:
          im = cv2.imread(imdb.image_path_at(i))
          im2show = np.copy(im)
      for j in xrange(1, imdb.num_classes):
          inds = torch.nonzero(scores[:,j]>thresh).view(-1)
          # if there is det
          if inds.numel() > 0:
            cls_scores = scores[:,j][inds]
            _, order = torch.sort(cls_scores, 0, True)
            if args.class_agnostic:
              cls_boxes = pred_boxes[inds, :]
            else:
              cls_boxes = pred_boxes[inds][:, j * 4:(j + 1) * 4]

            cls_dets = torch.cat((cls_boxes, cls_scores.unsqueeze(1)), 1)
            # cls_dets = torch.cat((cls_boxes, cls_scores), 1)
            cls_dets = cls_dets[order]
            keep = nms(cls_boxes[order, :], cls_scores[order], cfg.TEST.NMS)
            cls_dets = cls_dets[keep.view(-1).long()]
            if vis:
              im2show = vis_detections(im2show, imdb.classes[j], cls_dets.cpu().numpy(), 0.3)
            all_boxes[j][i] = cls_dets.cpu().numpy()
          else:
            all_boxes[j][i] = empty_array

      # Limit to max_per_image detections *over all classes*
      if max_per_image > 0:
          image_scores = np.hstack([all_boxes[j][i][:, -1]
                                    for j in xrange(1, imdb.num_classes)])
          if len(image_scores) > max_per_image:
              image_thresh = np.sort(image_scores)[-max_per_image]
              for j in xrange(1, imdb.num_classes):
                  keep = np.where(all_boxes[j][i][:, -1] >= image_thresh)[0]
                  all_boxes[j][i] = all_boxes[j][i][keep, :]

      misc_toc = time.time()
      nms_time = misc_toc - misc_tic

      if args.use_tfboard:
        #   info = {
        #     'loss': loss_temp,
        #     'loss_rpn_cls': loss_rpn_cls,
        #     'loss_rpn_box': loss_rpn_box,
        #     'loss_rcnn_cls': loss_rcnn_cls,
        #     'loss_rcnn_box': loss_rcnn_box,
        #     # 'loss_feat': loss_feat
        #   }
        #   logger.add_scalars("logs_s_{}/losses".format(args.checksession), info, 1 * num_images + i)

          import torchvision.utils as vutils
          x1 = vutils.make_grid(im_data, normalize=True, scale_each=True)
          logger.add_image("images_s_{}/input_3ch_image".format(args.checksession), x1, num_images + i)

          x2 = vutils.make_grid(im_data_1, normalize=True, scale_each=True)
          logger.add_image("images_s_{}/generated_first_domain".format(args.checksession), x2, num_images + i)


          # x2 = vutils.make_grid(im_data_1, normalize=True, scale_each=True)
          # from PIL import Image
          # logger.add_figure("images_s_{}/bbox_pred".format(args.checksession), Image.fromarray(im2show), num_images + i)

      sys.stdout.write('im_detect: {:d}/{:d} {:.3f}s {:.3f}s   \r' \
          .format(i + 1, num_images, detect_time, nms_time))
      sys.stdout.flush()

      if vis:
          # cv2.imwrite(f'images_output_better_new/{roidb[i]["image"].split("/")[-1].replace("jpg", "png}', im2show)
          # pdb.set_trace()
          cv2.imshow('test', im2show)
          cv2.waitKey(0)

  with open(det_file, 'wb') as f:
      pickle.dump(all_boxes, f, pickle.HIGHEST_PROTOCOL)

  print('Evaluating detections')
  imdb.evaluate_detections(all_boxes, output_dir)

  end = time.time()
  print("test time: %0.4fs" % (end - start))

