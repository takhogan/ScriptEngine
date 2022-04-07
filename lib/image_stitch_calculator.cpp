#include <tuple>
#include <iostream>
#include <opencv2/opencv.hpp>

using namespace std;
class ImageStitchCalculator {
    public:

        static vector<tuple<float, float>> calculateStitch(vector<string> imgPaths, vector<string> maskPaths) {
            auto pathToImg = [] (string pathName) {return cv::imread(pathName);};
            vector<cv::Mat> imgs;
            transform(imgPaths.begin(), imgPaths.end(), back_inserter(imgs), pathToImg);
            auto pathToMask = [] (string pathName) {return cv::imread(pathName, cv::IMREAD_GRAYSCALE).getUMat( cv::ACCESS_READ );};
            vector<cv::UMat> masks;
            transform(maskPaths.begin(), maskPaths.end(), back_inserter(masks), pathToMask);
            cv::Ptr<cv::Stitcher> stitcher = cv::Stitcher::create(cv::Stitcher::SCANS);
            // cout << "size1: " << imgs[0].size() << ",";
            // cout << "size2: " << masks[0].size() << ",";
            // cv::Mat outputPanorama;
            // stitcher->stitch(imgs, masks, outputPanorama);
            stitcher->estimateTransform(imgs, masks);
            vector<cv::detail::CameraParams> cameras = stitcher->cameras();
            vector<tuple<float,float>> transforms;
            const auto cameraToTransform = [](cv::detail::CameraParams camera) {
                return make_tuple(camera.R.at<float>(0,2), camera.R.at<float>(1,2));
            };
            transform(cameras.begin(), cameras.end(), back_inserter(transforms), cameraToTransform);
            // for (int i = 0; i < cameras.size(); i++) {
            //     cv::Mat r = cameras[i].R;
            //     cv::Mat t = cameras[i].t;
            //     cv::Mat oneRow = r.reshape(0,1);    // Treat as vector 
            //     std::ostringstream os;
            //     os << oneRow;                             // Put to the stream
            //     std::string asStr = os.str();             // Get string 
            //     asStr.pop_back();                         // Remove brackets
            //     asStr.erase(0,1);
            //     cout << "res_mat :" << asStr <<endl;
            // }
            // cout << transform_x << ",";
            // cout << transform_y << ",";
            // vector<cv::Mat> colorMasks;
            // stitcher->setTransform(imgs, cameras);
            // for (int maskIndex = 0; maskIndex < masks.size(); maskIndex++) {
            //     cv::Mat colorMask;
            //     cv::cvtColor(masks[maskIndex], colorMask, cv::COLOR_GRAY2BGR);
            //     colorMasks.push_back(colorMask);
            // }
            // auto maskToColorMask = [] (cv::UMat mask) {return cv::cvtColor(mask, mask, cv::COLOR_GRAY2BGR);};
            // transform(masks.begin(),masks.end(), back_inserter(colorMasks), maskToColorMask);
            // cout << colorMasks[0].channels() << ";";
            // stitcher->composePanorama(colorMasks, outputPanorama);
            // cv::UMat resultMaskRemasked(resultMask.rows, resultMask.cols, CV_8U, 0);
            // cout << "size: " << resultMaskRemasked.size() << ",";
            // cout << "size1: " << resultMaskRemasked(cv::Rect((int) transform_x * -1, 0, masks[0].cols, masks[0].rows)).size() << ",";
            // cout << "size2: " << masks[0].size() << ".";
            // masks[0].copyTo(resultMaskRemasked(cv::Rect((int) transform_x * -1, 0, masks[0].cols, masks[0].rows)));
            // cv::bitwise_or(
            //     resultMaskRemasked(cv::Rect(0, (int) transform_y, masks[0].cols, masks[0].rows)),
            //     masks[0], 
            //     resultMaskRemasked(cv::Rect(0, (int) transform_y, masks[0].cols, masks[0].rows))
            // );
            // cv::imwrite("result_mask_output.png", outputPanorama);
            return transforms;
        }
};

int main(int argc, char** argv) {
    // string panoramaFilePath = argv[1];
    // string appendFilePath = argv[2];
    // cout << "welcome!";
    // cout << panoramaFilePath;
    // cout << appendFilePath;
    // ImageStitchCalculator::calculateStitch(panoramaFilePath,appendFilePath);
    vector<string> imgPaths;
    vector<string> maskPaths;
    bool isImgPaths = true;
    for (int argIndex = 1; argIndex < argc; argIndex++) {
        if (strcmp(argv[argIndex], "-m") == 0) {
            isImgPaths = false;
            continue;
        }
        if (isImgPaths) {
            imgPaths.push_back(argv[argIndex]);
        } else {
            maskPaths.push_back(argv[argIndex]);
        }
        // cout << argv[argIndex] << ":" << argIndex << ",";
    }
    // cout << imgPaths.size() << ",";
    // cout << maskPaths.size() << ",";
    vector<tuple<float, float>> stitchCalcResult = ImageStitchCalculator::calculateStitch(imgPaths, maskPaths);
    cout << "[";
    for (int resultIndex = 0; resultIndex < stitchCalcResult.size(); resultIndex++) {
        cout << "(" << get<0>(stitchCalcResult[resultIndex]) << "," << get<1>(stitchCalcResult[resultIndex]) << ")";
        if ((resultIndex + 1) != stitchCalcResult.size()) {
            cout << ",";
        }
    }
    cout << "]";
    return 0;
}