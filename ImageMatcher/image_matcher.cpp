#include <opencv2/opencv.hpp>
#include <iostream>
#include <vector>
#include <cmath>
#include <map>
#include <string>
#include <tuple>
#include <algorithm>

const double MINIMUM_MATCH_PIXEL_SPACING = /*some_value*/;

#include <iostream>
#include <opencv2/opencv.hpp>
#include <map>
#include <string>
#include <vector>
#include <tuple>

std::vector<std::map<std::string, cv::Point>>
template_match(
    std::map<std::string, std::map<std::string, std::string>> detectObject,
    cv::Mat screencap_im_bgr,
    cv::Mat screencap_search_bgr,
    cv::Mat screencap_mask_gray,
    cv::Mat screencap_outputmask_bgr,
    cv::Mat screencap_outputmask_gray,
    std::string detector_name,
    std::string logs_path,
    std::string script_mode,
    cv::Point match_point,
    std::string log_level = "info",
    bool check_image_scale = true,
    cv::Rect output_cropping = cv::Rect(),
    double threshold = 0.96,
    bool use_color = true,
    bool use_mask = true) {

    std::vector<std::tuple<cv::Point, double, cv::Mat>> matches;
    cv::Mat match_result, result_im_bgr;

    if (detector_name == "pixelDifference") {
        std::tie(matches, match_result, result_im_bgr) = produce_template_matches(
            detectObject,
            screencap_im_bgr.clone(),
            screencap_search_bgr.clone(),
            screencap_mask_gray,
            screencap_outputmask_bgr,
            logs_path,
            std::stoi(detectObject["actionData"]["sourceScreenHeight"]),
            std::stoi(detectObject["actionData"]["sourceScreenWidth"]),
            log_level,
            check_image_scale,
            output_cropping,
            threshold,
            use_color,
            use_mask
        );
    }
    else if (detector_name == "scaledPixelDifference") {
        // Implement this case
    }
    else if (detector_name == "logisticClassifier") {
        std::cout << "logistic detector unimplemented" << std::endl;
        exit(0);
    }
    else {
        std::cout << "detector unimplemented!" << std::endl;
        exit(0);
    }

    int h = screencap_outputmask_gray.rows;
    int w = screencap_outputmask_gray.cols;

    if (log_level == "info") {
        cv::imwrite(logs_path + "matching_overlay.png", result_im_bgr);
        cv::imwrite(logs_path + "match_result.png", match_result * 255);
        cv::imwrite(logs_path + "output_mask.png", screencap_outputmask_gray);
    }

    int n_matches = matches.size();
    std::cout << "matches : ";

    for (const auto& [match, score, match_area] : matches) {
        std::cout << match << " ";
    }

    std::cout << match_point << std::endl;

    std::vector<std::map<std::string, cv::Point>> results;

    for (const auto& [match, score, match_area] : matches) {
        std::map<std::string, cv::Point> result;
        result["input_type"] = "shape";
        result["point"] = match_point == cv::Point() ? match : match + match_point;
        result["shape"] = screencap_outputmask_gray;
        result["matched_area"] = match_area;
        result["height"] = h;
        result["width"] = w;
        result["score"] = score;
        result["n_matches"] = n_matches;
        results.push_back(result);
    }

    return results;
}

std::tuple<std::vector<std::tuple<cv::Point, double, cv::Mat>>, cv::Mat, cv::Mat>
produce_template_matches(
    std::map<std::string, std::map<std::string, std::string>> detectObject,
    cv::Mat screencap_im_bgr,
    cv::Mat screencap_search_bgr,
    cv::Mat screencap_mask_gray,
    cv::Mat screencap_outputmask_bgr,
    std::string logs_path,
    int source_screen_height,
    int source_screen_width,
    bool check_image_scale,
    std::string log_level = "info",
    cv::Rect output_cropping = cv::Rect(),
    double threshold = 0.96,
    bool use_color = true,
    bool use_mask = true,
    std::string script_mode = "test") {

    int capture_height = screencap_im_bgr.rows;
    int capture_width = screencap_im_bgr.cols;
    bool is_dims_mismatch = check_image_scale && (capture_width != source_screen_width || capture_height != source_screen_height);
    double height_translation = 1.0;
    double width_translation = 1.0;
    cv::Mat match_result;
    cv::Mat mask;

    auto use_resized_im_only = detectObject["actionData"]["useImageRescaledToScreenOnly"] == "true";

    if (!use_resized_im_only) {
        try {
            cv::Mat image = use_color ? screencap_im_bgr : screencap_im_bgr.clone();
            cv::Mat templ = use_color ? screencap_search_bgr : screencap_search_bgr.clone();
            if (!use_color) {
                cv::cvtColor(image, image, cv::COLOR_BGR2GRAY);
                cv::cvtColor(templ, templ, cv::COLOR_BGR2GRAY);
            }
            mask = use_mask ? screencap_mask_gray : cv::Mat();
            cv::matchTemplate(image, templ, match_result, cv::TM_CCOEFF_NORMED, mask);
        } catch (cv::Exception& e) {
            std::cerr << "Error in matchTemplate: " << e.what() << std::endl;
            // handle error
        }
    }

    if (is_dims_mismatch || use_resized_im_only) {
        try {
            cv::Mat screencap_im_bgr_resized;
            cv::resize(screencap_im_bgr, screencap_im_bgr_resized, cv::Size(source_screen_width, source_screen_height), 0, 0, cv::INTER_AREA);

            cv::Mat image = use_color ? screencap_im_bgr_resized : screencap_im_bgr_resized.clone();
            cv::Mat templ = use_color ? screencap_search_bgr : screencap_search_bgr.clone();
            if (!use_color) {
                cv::cvtColor(image, image, cv::COLOR_BGR2GRAY);
                cv::cvtColor(templ, templ, cv::COLOR_BGR2GRAY);
            }
            mask = use_mask ? screencap_mask_gray : cv::Mat();
            cv::matchTemplate(image, templ, match_result, cv::TM_CCOEFF_NORMED, mask);

            height_translation = static_cast<double>(capture_height) / source_screen_height;
            width_translation = static_cast<double>(capture_width) / source_screen_width;

        } catch (cv::Exception& e) {
            std::cerr << "Error in matchTemplate: " << e.what() << std::endl;
            // handle error
        }
    }

    // Assuming filter_matches_and_get_result_im is implemented
    return filter_matches_and_get_result_im(
        detectObject,
        match_result,
        // ... other parameters ...
    );
}


double dist(double x1, double y1, double x2, double y2) {
    return std::sqrt((x2 - x1) * (x2 - x1) + (y2 - y1) * (y2 - y1));
}

std::pair<int, int> adjust_box_to_bounds(const cv::Point& pt, int box_width, int box_height, int screen_width, int screen_height, int box_thickness) {
    int x_overshoot = pt.x + box_width + box_thickness - screen_width;
    int y_overshoot = pt.y + box_height + box_thickness - screen_height;
    return {std::max(0, box_width - (x_overshoot > 0 ? x_overshoot : 0)),
            std::max(0, box_height - (y_overshoot > 0 ? y_overshoot : 0))};
}

std::tuple<std::vector<std::tuple<cv::Point, double, cv::Mat>>, cv::Mat, cv::Mat>
filter_matches_and_get_result_im(
    const cv::Mat& detectObject, const cv::Mat& match_result,
    std::vector<cv::Point> thresholded_match_results,
    const cv::Mat& screencap_im_bgr, const cv::Mat& screencap_search_bgr,
    const cv::Mat& screencap_outputmask_bgr,
    const std::string& logs_path, const std::string& log_level = "info",
    double height_translation = 1, double width_translation = 1,
    const std::string& script_mode = "test", cv::Rect output_cropping = cv::Rect(-1, -1, -1, -1)
) {
    int h = screencap_search_bgr.rows;
    int w = screencap_search_bgr.cols;

    double dist_threshold = std::max((w + h) * 0.1, MINIMUM_MATCH_PIXEL_SPACING);
    std::vector<std::tuple<cv::Point, double, cv::Mat>> matches;
    int match_img_index = 1;

    // Assuming match_result is a cv::Mat object and elements can be accessed by match_result.at<double>(row, col)
    for (const auto& pt : thresholded_match_results) {
        bool redundant = false;
        double match_score = match_result.at<double>(pt.y, pt.x);

        cv::Mat roi = screencap_im_bgr(cv::Rect(pt.x, pt.y, w, h)).clone();
        cv::Mat match_img_bgr;
        cv::bitwise_and(roi, screencap_outputmask_bgr, match_img_bgr);

        if (output_cropping.width > 0 && output_cropping.height > 0) {
            match_img_bgr = match_img_bgr(output_cropping).clone();
        }

        if (match_score == INFINITY) {
            continue;
        }

        double adjusted_pt_x = pt.x * width_translation;
        double adjusted_pt_y = pt.y * height_translation;

        for (size_t match_index = 0; match_index < matches.size(); ++match_index) {
            auto [match_coord, existing_match_score, _] = matches[match_index];
            double match_dist = dist(match_coord.x, match_coord.y, adjusted_pt_x, adjusted_pt_y);

            if (match_dist < dist_threshold) {
                if (match_score > existing_match_score) {
                    matches[match_index] = {cv::Point(adjusted_pt_x, adjusted_pt_y), match_score, match_img_bgr};
                }
                redundant = true;
                break;
            }
        }

        if (!redundant) {
            matches.push_back({cv::Point(adjusted_pt_x, adjusted_pt_y), match_score, match_img_bgr});
            match_img_index++;
        }
    }


    // Find best match
    std::string best_match = "none";
    cv::Point best_match_pt;
    cv::Mat inf_mask = (match_result != INFINITY);
    double minVal, maxVal;
    cv::Point minLoc, maxLoc;
    cv::minMaxLoc(match_result, &minVal, &maxVal, &minLoc, &maxLoc, inf_mask);
    
    if (maxVal != -INFINITY) {
        best_match_pt = maxLoc;
        best_match = std::to_string(maxVal);
    } else {
        std::cout << "a not valid" << std::endl;
    }

    std::cout << "n matches: " << matches.size() << " best match: " << best_match_pt << ", " << best_match << std::endl;

    cv::Mat result_im_bgr = screencap_im_bgr.clone();

    // Sort matches
    std::sort(matches.begin(), matches.end(),
              [](const auto& a, const auto& b) {
                  return std::get<1>(a) > std::get<1>(b);
              });

    // Drawing rectangles
    int box_w, box_h;
    for (const auto& pt : thresholded_match_results) {
        // Assuming adjust_box_to_bounds is a function that returns a pair of new dimensions (box_w, box_h)
        std::tie(box_w, box_h) = adjust_box_to_bounds(pt, w, h, screencap_im_bgr.cols, screencap_im_bgr.rows, 2);
        cv::rectangle(result_im_bgr, pt, cv::Point(pt.x + box_w, pt.y + box_h), cv::Scalar(0, 0, 255), 2);
    }

    if (thresholded_match_results.empty() && best_match_pt != cv::Point(-1, -1)) {
        std::tie(box_w, box_h) = adjust_box_to_bounds(best_match_pt, w, h, screencap_im_bgr.cols, screencap_im_bgr.rows, 2);
        cv::rectangle(result_im_bgr, best_match_pt, cv::Point(best_match_pt.x + box_w, best_match_pt.y + box_h), cv::Scalar(0, 0, 128), 2);
    }

    std::cout << "box_w, box_h: " << box_w << ", " << box_h << std::endl;

    return {matches, match_result, screencap_im_bgr};  // or whatever you need to return
}

int main() {
    // Your main function code here
    return 0;
}
