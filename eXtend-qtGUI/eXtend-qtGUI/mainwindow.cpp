#include "mainwindow.h"
#include "ui_mainwindow.h"

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

void MainWindow::on_pushButton_clicked()
{
    setEnabled(false);
    std::string sshAddressUsername = ui->sshAddressUsername->text().toStdString();
    std::string sshAddressServer = ui->sshAddressServer->text().toStdString();

    system((std::string() + "bash eXtend_alpha_setup.sh " + sshAddressUsername + "@" + sshAddressServer).c_str());
}
