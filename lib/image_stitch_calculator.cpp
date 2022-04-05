#include <tuple>
#include <iostream>
#include <opencv2/opencv.hpp>

using namespace std;
class ImageStitchCalculator {
    public:

        static tuple<float, float> calculateStitch(vector<string> imgPaths, vector<string> masks) {
            imgPaths = {"..\\logs\\SearchScriptBasic-2022-04-03 16-57-28\\search_patterns\\searchPattern-1\\10-0.3920703541226584--1.209056554131917-search-step-complete.png",
                                "..\\logs\\SearchScriptBasic-2022-04-03 16-57-28\\search_patterns\\searchPattern-1\\10-0.3920703541226584--1.209056554131917-search-step-init.png"};
            auto pathToImg = [] (string pathName) {return cv::imread(pathName);};
            vector<cv::Mat> imgs;
            transform(imgPaths.begin(), imgPaths.end(), back_inserter(imgs), pathToImg);
            // transform(masks.begin(), masks.end(), masks.begin(), pathToImg);
            // cv::Mat outputPanorama;
            // cv::Ptr<cv::Stitcher> stitcher = cv::Stitcher::create(cv::Stitcher::SCANS);
            // stitcher->estimateTransform(imgs);
            // vector<cv::detail::CameraParams> cameras = stitcher->cameras();
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
            // stitcher->stitch(imgs, outputPanorama);
            // cv::imwrite("image_stitcher_output.png", outputPanorama);
            return {0, 0};
        }
};

int main(int argc, char** argv) {
    // string panoramaFilePath = argv[1];
    // string appendFilePath = argv[2];
    // cout << "welcome!";
    // cout << panoramaFilePath;
    // cout << appendFilePath;
    // ImageStitchCalculator::calculateStitch(panoramaFilePath,appendFilePath);
    ImageStitchCalculator::calculateStitch({""},{""});
}