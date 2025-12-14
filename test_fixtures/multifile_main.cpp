// Multi-file test - main file
#include <iostream>
#include "multifile_helper.h"

int main() {
    int value = 42;  // Line 6

    int doubled = helper_double(value);  // Line 8
    int squared = helper_square(value);  // Line 9

    std::cout << "Value: " << value << std::endl;  // Line 11
    std::cout << "Doubled: " << doubled << std::endl;  // Line 12
    std::cout << "Squared: " << squared << std::endl;  // Line 13

    return 0;
}
