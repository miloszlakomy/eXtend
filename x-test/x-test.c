#include <X11/Xlib.h>
#include <X11/X.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#pragma pack(1)
typedef struct tagBITMAPFILEHEADER {
    uint16_t    bfType;
    uint32_t   bfSize;
    uint16_t    bfReserved1;
    uint16_t    bfReserved2;
    uint32_t   bfOffBits;
} BITMAPFILEHEADER;

typedef struct tagBITMAPINFOHEADER{
    uint32_t  biSize;
    int32_t   biWidth;
    int32_t   biHeight;
    uint16_t   biPlanes;
    uint16_t   biBitCount;
    uint32_t  biCompression;
    uint32_t  biSizeImage;
    int32_t   biXPelsPerMeter;
    int32_t   biYPelsPerMeter;
    uint32_t  biClrUsed;
    uint32_t  biClrImportant;
} BITMAPINFOHEADER;
#pragma pack()

void saveXImageToBitmap(XImage *pImage, const char *filename)
{
    BITMAPFILEHEADER bmpFileHeader;
    BITMAPINFOHEADER bmpInfoHeader;
    FILE *fp;
    int dummy;
    memset(&bmpFileHeader, 0, sizeof(BITMAPFILEHEADER));
    memset(&bmpInfoHeader, 0, sizeof(BITMAPINFOHEADER));
    bmpFileHeader.bfType = 0x4D42;
    bmpFileHeader.bfSize = sizeof(BITMAPFILEHEADER) + sizeof(BITMAPINFOHEADER) +  pImage->width*pImage->height*4;
    bmpFileHeader.bfOffBits = sizeof(BITMAPFILEHEADER) + sizeof(BITMAPINFOHEADER);
    bmpFileHeader.bfReserved1 = 0;
    bmpFileHeader.bfReserved2 = 0;

    bmpInfoHeader.biSize = sizeof(BITMAPINFOHEADER);
    bmpInfoHeader.biWidth = pImage->width;
    bmpInfoHeader.biHeight = pImage->height;
    bmpInfoHeader.biPlanes = 1;
    bmpInfoHeader.biBitCount = 32;
    dummy = (pImage->width * 3) % 4;
    if((4-dummy)==4)
        dummy=0;
    else
        dummy=4-dummy;
    bmpInfoHeader.biSizeImage = ((pImage->width*3)+dummy)*pImage->height;
    bmpInfoHeader.biCompression = 0;
    bmpInfoHeader.biXPelsPerMeter = 0;
    bmpInfoHeader.biYPelsPerMeter = 0;
    bmpInfoHeader.biClrUsed = 0;
    bmpInfoHeader.biClrImportant = 0;

    fp = fopen(filename, "wb");

    if(fp == NULL)
        return;

    fwrite(&bmpFileHeader, sizeof(bmpFileHeader), 1, fp);
    fwrite(&bmpInfoHeader, sizeof(bmpInfoHeader), 1, fp);

    for (int32_t i = pImage->height - 1; i >= 0; --i) {
        fwrite(pImage->data + i * pImage->width * 4, pImage->width * 4, 1, fp);
    }

    fclose(fp);
}

int main(int argc, char **argv)
{
    if (argc < 6) {
        fprintf(stderr, "usage: %s out_file x_offset y_offset width height", argv[0]);
        return 1;
    }

    const char *outFilename = argv[1];
    const uint32_t X_OFFSET = atoi(argv[2]);
    const uint32_t Y_OFFSET = atoi(argv[3]);
    const uint32_t WIDTH = atoi(argv[4]);
    const uint32_t HEIGHT = atoi(argv[5]);

    if (WIDTH == 0 || HEIGHT == 0) {
        fprintf(stderr, "width & height must be greater than 0");
        return 1;
    }

    Display *dpy = XOpenDisplay(NULL);
    Window root = DefaultRootWindow(dpy);

    XImage *sshot = XCreateImage(dpy, CopyFromParent,
                                 32, ZPixmap, 0, NULL,
                                 WIDTH, HEIGHT, BitmapPad(dpy), 0);
    if (!sshot) {
        fprintf(stderr, "XCreateImage\n");
        return 1;
    }

    sshot->data = malloc(WIDTH * HEIGHT * 4);

    XImage *img = XGetSubImage(dpy, root,
                               X_OFFSET, Y_OFFSET, WIDTH, HEIGHT,
                               AllPlanes, ZPixmap,
                               sshot, 0, 0);
    if (!img) {
        fprintf(stderr, "XGetSubImage\n");
        return 1;
    }

    saveXImageToBitmap(img, outFilename);

    free(sshot->data);

    return 0;
}
