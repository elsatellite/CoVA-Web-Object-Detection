import argparse
import numpy as np
import os
import torch
import torch.nn as nn
import torch.optim as optim

from datasets import load_data
from models import WebObjExtractionNet
from train import train_model, evaluate_model
from utils import print_and_log


########## CMDLINE ARGS ##########
parser = argparse.ArgumentParser('Train Model')
parser.add_argument('-d', '--device', type=int, default=0)
parser.add_argument('-e', '--n_epochs', type=int, default=50)
parser.add_argument('-bb', '--backbone', type=str, default='alexnet', choices=['alexnet', 'resnet'])
parser.add_argument('-tc', '--trainable_convnet', type=int, default=1, choices=[0,1])
parser.add_argument('-lr', '--learning_rate', type=float, default=0.0005)
parser.add_argument('-bs', '--batch_size', type=int, default=5)
parser.add_argument('-wd', '--weight_decay', type=float, default=0.0)
parser.add_argument('-r', '--roi', type=int, default=3)
parser.add_argument('-w', '--weighted_loss', type=int, default=0, choices=[0,1])
parser.add_argument('-pf', '--pos_feat', type=int, default=0, choices=[0,1])
parser.add_argument('-nw', '--num_workers', type=int, default=4)
args = parser.parse_args()

device = torch.device('cuda:%d' % args.device if torch.cuda.is_available() else 'cpu')

########## MAKING RESULTS REPRODUCIBLE ##########
seed = 1
np.random.seed(seed)
torch.manual_seed(seed)
# torch.backends.cudnn.deterministic = True
# torch.backends.cudnn.benchmark = False

########## PARAMETERS ##########
N_CLASSES = 4
CLASS_NAMES = ['BG', 'Price', 'Title', 'Image']
IMG_HEIGHT = 1280 # Image assumed to have same height and width
EVAL_INTERVAL = 5 # Number of Epochs after which model is evaluated
NUM_WORKERS = args.num_workers # multithreaded data loading

DATA_DIR = '../data/' # Contains .png and .pkl files for train and test data
OUTPUT_DIR = 'results' # logs are saved here! 
# NOTE: if same hyperparameter configuration is run again, previous log file and saved model will be overwritten

SPLIT_DIR = 'splits/random' # contains train, val, test split files
# each line in these files should contain name of the training image (without file extension)
TRAIN_SPLIT_ID_FILE = SPLIT_DIR+ '/train_imgs.txt'
VAL_SPLIT_ID_FILE = SPLIT_DIR + '/val_imgs.txt'
TEST_SPLIT_ID_FILE = SPLIT_DIR + '/test_imgs.txt'

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)
    
train_img_ids = np.loadtxt(TRAIN_SPLIT_ID_FILE, dtype=np.int32)
val_img_ids = np.loadtxt(VAL_SPLIT_ID_FILE, dtype=np.int32)
test_img_ids = np.loadtxt(TEST_SPLIT_ID_FILE, dtype=np.int32)

########## HYPERPARAMETERS ##########
N_EPOCHS = args.n_epochs
BACKBONE = args.backbone
TRAINABLE_CONVNET = bool(args.trainable_convnet)
LEARNING_RATE = args.learning_rate
BATCH_SIZE = args.batch_size
WEIGHT_DECAY = args.weight_decay
ROI_POOL_OUTPUT_SIZE = (args.roi, args.roi)
WEIGHTED_LOSS = bool(args.weighted_loss)
POS_FEAT = bool(args.pos_feat)

if WEIGHTED_LOSS:
    weights = torch.Tensor([1,100,100,100]) # weight inversely proportional to number of examples for the class
    print('Weighted loss with class weights:', weights)
else:
    weights = torch.ones(N_CLASSES)

params = '%s lr-%.0e batch-%d wd-%.0e roi-%d wt_loss-%d pf-%d' % (BACKBONE, LEARNING_RATE, BATCH_SIZE, WEIGHT_DECAY, ROI_POOL_OUTPUT_SIZE[0], WEIGHTED_LOSS, POS_FEAT)
log_file = '%s/%s logs.txt' % (OUTPUT_DIR, params)
model_save_file = '%s/%s saved_model.pth' % (OUTPUT_DIR, params)

print('logs will be saved in \"%s\"' % (log_file))
print_and_log('Backbone Convnet: %s' % (BACKBONE), log_file, 'w')
print_and_log('Trainable Convnet: %s' % (TRAINABLE_CONVNET), log_file)
print_and_log('Learning Rate: %.0e' % (LEARNING_RATE), log_file)
print_and_log('Batch Size: %d' % (BATCH_SIZE), log_file)
print_and_log('Weight Decay: %.0e' % (WEIGHT_DECAY), log_file)
print_and_log('RoI Pool Output Size: (%d, %d)' % ROI_POOL_OUTPUT_SIZE, log_file)
print_and_log('Weighted Loss: %s' % (WEIGHTED_LOSS), log_file)
print_and_log('Position Features: %s\n' % (POS_FEAT), log_file)

########## DATA LOADERS ##########
train_loader, val_loader, test_loader = load_data(DATA_DIR, train_img_ids, val_img_ids, test_img_ids, BATCH_SIZE, NUM_WORKERS)

########## CREATE MODEL & LOSS FN ##########
model = WebObjExtractionNet(ROI_POOL_OUTPUT_SIZE, IMG_HEIGHT, N_CLASSES, BACKBONE, TRAINABLE_CONVNET, POS_FEAT, CLASS_NAMES).to(device)

optimizer = optim.Adam(model.parameters(), lr=LEARNING_RATE, weight_decay=WEIGHT_DECAY)
criterion = nn.CrossEntropyLoss(weight=weights, reduction='sum').to(device)

########## TRAIN MODEL ##########
train_model(model, train_loader, optimizer, criterion, N_EPOCHS, device, val_loader, EVAL_INTERVAL, log_file, 'ckpt_%d.pth' % args.device)

########## EVALUATE TEST PERFORMANCE ##########
evaluate_model(model, test_loader, criterion, device, 'TEST', log_file)

########## SAVE MODEL ##########
torch.save(model.state_dict(), model_save_file)
print_and_log('Model can be restored from \"%s\"' % (model_save_file), log_file)
