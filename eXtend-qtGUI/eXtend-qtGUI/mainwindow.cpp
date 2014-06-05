#include "mainwindow.h"
#include "ui_mainwindow.h"

#include <iostream>
#include <cstdio>
#include <queue>
#include <thread>

MainWindow::MainWindow(QWidget *parent) :
    QMainWindow(parent),
    ui(new Ui::MainWindow)
{
    ui->setupUi(this);
}

MainWindow::~MainWindow()
{
    delete ui;
}

std::string exec(const char* cmd, bool verbose = true) {
    if(verbose)
        std::cout << cmd << std::endl;

    FILE* pipe = popen(cmd, "r");
    if (!pipe) return "ERROR";
    char buffer[128];
    std::string result = "";
    while(!feof(pipe)) {
        if(fgets(buffer, 128, pipe) != NULL)
            result += buffer;
    }
    pclose(pipe);

    if(verbose)
        std::cout << result << std::endl;

    return result;
}

void MainWindow::on_pushButton_clicked()
{
    setEnabled(false);
    const std::string& sshAddressUsername = ui->sshAddressUsername->text().toStdString();
    const std::string& sshAddressServer = ui->sshAddressServer->text().toStdString();

    const std::string sshAddress = sshAddressUsername + "@" + sshAddressServer;

    std::thread([sshAddress, this](){
        exec((std::string() + "ssh \"" + sshAddress + "\" \"xrandr -display :0 | head -1 | sed 's/.*current \\([0-9]\\+\\)\\+ x \\([0-9]\\+\\)\\+.*/\\1x\\2/' && xrandr -display :0 | grep -o '[0-9]\\+x[0-9]\\++[0-9]\\++[0-9]\\+'\"").c_str());
        setEnabled(true);
    }).detach();
}

void MainWindow::on_pushButton_2_clicked()
{
    const std::string& sshAddressUsername = ui->sshAddressUsername->text().toStdString();
    const std::string& sshAddressServer = ui->sshAddressServer->text().toStdString();

    const std::string sshAddress = sshAddressUsername + "@" + sshAddressServer;

    std::thread([sshAddress](){
        exec((std::string() + "bash ../../eXtend_alpha_setup.sh " + sshAddress).c_str());
    }).detach();
}

void MainWindow::on_pushButton_3_clicked()
{
//    const std::string& sshAddressUsername = ui->sshAddressUsername->text().toStdString();
    const std::string& sshAddressServer = ui->sshAddressServer->text().toStdString();

//    const std::string sshAddress = sshAddressUsername + "@" + sshAddressServer;

    const std::string& vncDisplay = ui->vncDisplay->text().toStdString();

    std::thread([sshAddressServer, vncDisplay](){
        exec((std::string() + "vncviewer " + sshAddressServer + vncDisplay + " -fullscreen").c_str());
    }).detach();
}
