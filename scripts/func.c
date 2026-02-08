bool func0(int arr[], int n, int x) {

    int i = binary_search(arr, 0, n-1, x);

    if (i == -1) {

        return false;

    }

    if ((i + n/2) <= (n -1) && arr[i + n/2] == x) {

        return true;

    } else {

        return false;

    }

}
