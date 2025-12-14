// Simple test program for basic breakpoint testing
#include <iostream>

int add(int a, int b) {
    int result = a + b;  // Line 6: good for breakpoint
    return result;
}

int multiply(int a, int b) {
    int result = a * b;  // Line 11
    return result;
}

int main(int argc, char* argv[]) {
    int x = 10;  // Line 16
    int y = 20;  // Line 17

    int sum = add(x, y);  // Line 19
    int product = multiply(x, y);  // Line 20

    std::cout << "Sum: " << sum << std::endl;  // Line 22
    std::cout << "Product: " << product << std::endl;  // Line 23

    return 0;
}
