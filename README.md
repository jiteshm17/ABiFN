# Multimodal Object Detection using Thermal and RGB Images

Generate a fused representation (feature map) of an RGB Image and it's corresponding thermal image for improving the accuracy (mean average precision score) for the task of object detection.
We are using a dataset where we have thermal images, corresponding RGB images and the groudtruths (labels) for the thermal images. 
We are exploring fusion techniques to fuse the RGB feature map and the thermal feature map obtained from a CNN to perform better in the domain of object detection

Objects classes for detection are car, person and bicycle

Dataset used is the FLIR dataset -> https://www.flir.in/oem/adas/adas-dataset-form/

# Acknowledgement

Most of the code is used and modified from the https://github.com/jwyang/faster-rcnn.pytorch repository
