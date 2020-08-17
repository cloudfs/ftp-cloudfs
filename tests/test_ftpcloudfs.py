#!/usr/bin/python
import unittest
import os
import sys
import ftplib
import StringIO
from datetime import datetime
from time import sleep
from swiftclient import client

from ftpcloudfs.constants import default_address, default_port, \
    default_ks_service_type, default_ks_endpoint_type, \
    default_ks_tenant_separator, default_ks_domain_separator
from ftpcloudfs.fs import ListDirCache


class FtpObjectStorageFSTest(unittest.TestCase):
    ''' FTP Cloud FS main test '''

    def setUp(self):
        if not all(['OS_API_KEY' in os.environ,
                    'OS_API_USER' in os.environ,
                    'OS_AUTH_URL' in os.environ,
                    ]):
            print "env OS_API_USER/OS_API_KEY/OS_AUTH_URL not found."
            sys.exit(1)

        self.username = os.environ['OS_API_USER']
        self.real_user = os.environ.get('OS_REAL_USER', self.username)
        self.api_key = os.environ['OS_API_KEY']
        self.auth_url = os.environ.get('OS_AUTH_URL')
        self.cnx = ftplib.FTP()
        self.cnx.host = default_address
        self.cnx.port = default_port
        self.cnx.connect()
        self.cnx.login(self.username, self.api_key)
        self.container = "ftpcloudfs_testing"
        self.cnx.mkd("/%s" % self.container)
        self.cnx.cwd("/%s" % self.container)

        kwargs = dict(authurl=self.auth_url, auth_version="1.0")

        region_name = os.environ.get('OS_KEYSTONE_REGION_NAME')
        if region_name:
            tenant_separator = os.environ.get('OS_KEYSTONE_TENANT_SEPARATOR', default_ks_tenant_separator)
            tenant_name, self.username = self.username.split(tenant_separator, 1)
            self.real_user = self.username

            kwargs['os_options'] = dict(
                service_type=os.environ.get('OS_KEYSTONE_SERVICE_TYPE', default_ks_service_type),
                endpoint_type=os.environ.get('OS_KEYSTONE_ENDPOINT_TYPE', default_ks_endpoint_type),
                region_name=region_name,
            )

            kwargs['auth_version'] = os.environ.get('OS_KEYSTONE_API_VERSION', '2.0')
            if kwargs['auth_version'] == "3":
                domain_separator = os.environ.get('OS_KEYSTONE_DOMAIN_SEPARATOR', default_ks_domain_separator)
                try:
                    self.username, user_domain_name = self.username.split(domain_separator, 1)
                except ValueError:
                    user_domain_name = "default"
                self.real_user = self.username

                try:
                    project_name, project_domain_name = tenant_name.split(domain_separator, 1)
                except ValueError:
                    project_name = tenant_name
                    project_domain_name = "default"

                kwargs["os_options"]["project_name"] = project_name
                kwargs["os_options"]["project_domain_name"] = project_domain_name
                kwargs["os_options"]["user_domain_name"] = user_domain_name
            else:
                kwargs["tenant_name"] = tenant_name

        self.conn = client.Connection(user=self.username, key=self.api_key, **kwargs)

    def create_file(self, path, contents):
        '''Create path with contents'''
        self.cnx.storbinary("STOR %s" % path, StringIO.StringIO(contents))

    def test_mkdir_chdir_rmdir(self):
        ''' mkdir/chdir/rmdir directory '''
        directory = "/foobarrandom"
        self.assertEqual(self.cnx.mkd(directory), directory)
        self.assertEqual(self.cnx.cwd(directory),
                         '250 "%s" is the current directory.' % (directory))
        self.assertEqual(self.cnx.rmd(directory), "250 Directory removed.")

    def test_mkdir_chdir_mkdir_rmdir_subdir(self):
        ''' mkdir/chdir/rmdir sub directory '''
        directory = "/foobarrandom"
        self.assertEqual(self.cnx.mkd(directory), directory)
        self.assertEqual(self.cnx.cwd(directory),
                         '250 "%s" is the current directory.' % (directory))
        subdirectory = "potato"
        subdirpath = directory + "/" + subdirectory
        self.assertEqual(self.cnx.mkd(subdirectory), subdirpath)
        # Can't delete a directory with stuff in
        self.assertRaises(ftplib.error_perm, self.cnx.rmd, directory)
        self.assertEqual(self.cnx.cwd(subdirectory),
                         '250 "%s" is the current directory.' % (subdirpath))
        self.assertEqual(self.cnx.cwd(".."),
                         '250 "%s" is the current directory.' % (directory))
        self.assertEqual(self.cnx.rmd(subdirectory), "250 Directory removed.")
        self.assertEqual(self.cnx.cwd(".."),
                         '250 "/" is the current directory.')
        self.assertEqual(self.cnx.rmd(directory), "250 Directory removed.")

    def test_write_open_delete(self):
        ''' write/open/delete file '''
        content_string = "Hello Moto"
        self.create_file("testfile.txt", content_string)
        self.assertEquals(self.cnx.size("testfile.txt"), len(content_string))
        store = StringIO.StringIO()
        self.cnx.retrbinary("RETR testfile.txt", store.write)
        self.assertEqual(store.getvalue(), content_string)
        self.assertEqual(self.cnx.delete("testfile.txt"), "250 File removed.")
        store.close()

    def test_write_open_delete_subdir(self):
        ''' write/open/delete file in a subdirectory'''
        self.cnx.mkd("potato")
        self.cnx.cwd("potato")
        content_string = "Hello Moto"
        self.create_file("testfile.txt", content_string)
        self.assertEquals(self.cnx.size("testfile.txt"), len(content_string))
        store = StringIO.StringIO()
        self.cnx.retrbinary("RETR /%s/potato/testfile.txt" % self.container, store.write)
        self.assertEqual(store.getvalue(), content_string)
        self.assertEqual(self.cnx.delete("testfile.txt"), "250 File removed.")
        self.cnx.cwd("..")
        self.cnx.rmd("potato")
        store.close()

    def test_write_to_slash(self):
        ''' write to slash should not be permitted '''
        self.cnx.cwd("/")
        content_string = "Hello Moto"
        self.assertRaises(ftplib.error_perm, self.create_file, "testfile.txt", content_string)

    def test_chdir_to_a_file(self):
        ''' chdir to a file '''
        self.create_file("testfile.txt", "Hello Moto")
        self.assertRaises(ftplib.error_perm, self.cnx.cwd, "/%s/testfile.txt" % self.container)
        self.cnx.delete("testfile.txt")

    def test_chdir_to_slash(self):
        ''' chdir to slash '''
        self.cnx.cwd("/")

    def test_chdir_to_nonexistent_container(self):
        ''' chdir to non existent container'''
        self.assertRaises(ftplib.error_perm, self.cnx.cwd, "/i_dont_exist")

    def test_chdir_to_nonexistent_directory(self):
        ''' chdir to nonexistend directory'''
        self.assertRaises(ftplib.error_perm, self.cnx.cwd, "i_dont_exist")
        self.assertRaises(ftplib.error_perm, self.cnx.cwd, "/%s/i_dont_exist" % self.container)

    def test_listdir_root(self):
        ''' list root directory '''
        self.cnx.cwd("/")
        ls = self.cnx.nlst()
        self.assertTrue(self.container in ls)
        self.assertTrue('potato' not in ls)
        self.cnx.mkd("potato")
        ls = self.cnx.nlst()
        self.assertTrue(self.container in ls)
        self.assertTrue('potato' in ls)
        self.cnx.rmd("potato")

    def test_listdir(self):
        ''' list directory '''
        content_string = "Hello Moto"
        self.create_file("testfile.txt", content_string)
        self.assertEqual(self.cnx.nlst(), ["testfile.txt"])
        lines = []
        self.assertEquals(self.cnx.retrlines('LIST', callback=lines.append), '226 Transfer complete.')
        self.assertEquals(len(lines), 1)
        line = lines[0]
        padding = " " + " "*(8-len(self.real_user))
        expected = "-rw-r--r--   1 "+self.real_user+padding+self.real_user+padding+"      10 "+ datetime.utcnow().strftime("%b %d %H:")
        self.assertTrue(line.startswith(expected), "line %r != expected %r" % (line, expected))
        self.assertTrue(line.endswith(" testfile.txt"))
        self.cnx.delete("testfile.txt")

    def test_listdir_subdir(self):
        ''' list a sub directory'''
        content_string = "Hello Moto"
        self.create_file("1.txt", content_string)
        self.create_file("2.txt", content_string)
        self.cnx.mkd("potato")
        self.create_file("potato/3.txt", content_string)
        self.create_file("potato/4.txt", content_string)
        self.assertEqual(self.cnx.nlst(), ["1.txt", "2.txt", "potato"])
        self.cnx.cwd("potato")
        self.assertEqual(self.cnx.nlst(), ["3.txt", "4.txt"])
        self.cnx.delete("3.txt")
        self.cnx.delete("4.txt")
        self.assertEqual(self.cnx.nlst(), [])
        self.cnx.cwd("..")
        self.cnx.delete("1.txt")
        self.cnx.delete("2.txt")
        self.assertEqual(self.cnx.nlst(), ["potato"])
        lines = []
        self.assertEquals(self.cnx.retrlines('LIST', callback=lines.append), '226 Transfer complete.')
        self.assertEquals(len(lines), 1)
        line = lines[0]
        padding = " " + " "*(8-len(self.real_user))
        expected = "drwxr-xr-x   1 "+self.real_user+padding+self.real_user+padding+"       0 "+ datetime.utcnow().strftime("%b %d %H:")
        self.assertTrue(line.startswith(expected), "line %r != expected %r" % (line, expected))
        self.assertTrue(line.endswith(" potato"))
        self.cnx.rmd("potato")
        self.assertEqual(self.cnx.nlst(), [])

    def test_rename_file(self):
        '''rename a file'''
        content_string = "Hello Moto" * 100
        self.create_file("testfile.txt", content_string)
        self.assertEquals(self.cnx.size("testfile.txt"), len(content_string))
        self.assertRaises(ftplib.error_perm, self.cnx.size, "testfile2.txt")
        self.cnx.rename("testfile.txt", "testfile2.txt")
        self.assertEquals(self.cnx.size("testfile2.txt"), len(content_string))
        self.assertRaises(ftplib.error_perm, self.cnx.size, "testfile.txt")
        self.cnx.delete("testfile2.txt")

    def test_rename_file_into_subdir1(self):
        '''rename a file into a subdirectory 1'''
        content_string = "Hello Moto"
        self.create_file("testfile.txt", content_string)
        self.cnx.mkd("potato")
        self.assertEquals(self.cnx.size("testfile.txt"), len(content_string))
        self.assertRaises(ftplib.error_perm, self.cnx.size, "potato/testfile3.txt")
        self.cnx.rename("testfile.txt", "potato/testfile3.txt")
        self.assertEquals(self.cnx.size("potato/testfile3.txt"), len(content_string))
        self.assertRaises(ftplib.error_perm, self.cnx.size, "testfile.txt")
        self.cnx.delete("potato/testfile3.txt")
        self.cnx.rmd("potato")

    def test_rename_file_into_subdir2(self):
        '''rename a file into a subdirectory without specifying dest leaf'''
        content_string = "Hello Moto"
        self.create_file("testfile.txt", content_string)
        self.cnx.mkd("potato")
        self.assertEquals(self.cnx.size("testfile.txt"), len(content_string))
        self.assertRaises(ftplib.error_perm, self.cnx.size, "potato/testfile.txt")
        self.cnx.rename("testfile.txt", "potato")
        self.assertEquals(self.cnx.size("potato/testfile.txt"), len(content_string))
        self.assertRaises(ftplib.error_perm, self.cnx.size, "testfile.txt")
        self.cnx.delete("potato/testfile.txt")
        self.cnx.rmd("potato")

    def test_rename_file_into_root(self):
        '''rename a file into a subdirectory without specifying dest leaf'''
        content_string = "Hello Moto"
        self.create_file("testfile.txt", content_string)
        self.assertRaises(ftplib.error_perm, self.cnx.rename, "testfile.txt", "/testfile.txt")
        self.cnx.delete("testfile.txt")

    def test_rename_directory_into_file(self):
        '''rename a directory into a file - shouldn't work'''
        content_string = "Hello Moto"
        self.create_file("testfile.txt", content_string)
        self.assertRaises(ftplib.error_perm, self.cnx.rename, "/%s" % self.container, "testfile.txt")
        self.cnx.delete("testfile.txt")

    def test_rename_directory_into_directory(self):
        '''rename a directory into a directory'''
        self.cnx.mkd("potato")
        self.assertEquals(self.cnx.nlst("potato"), [])
        self.cnx.rename("potato", "potato2")
        self.assertEquals(self.cnx.nlst("potato2"), [])
        self.cnx.rmd("potato2")

    def test_rename_directory_into_existing_directory(self):
        '''rename a directory into an existing directory'''
        self.cnx.mkd("potato")
        self.cnx.mkd("potato2")
        self.assertEquals(self.cnx.nlst("potato"), [])
        self.assertEquals(self.cnx.nlst("potato2"), [])
        self.cnx.rename("potato", "potato2")
        self.assertEquals(self.cnx.nlst("potato2"), ["potato"])
        self.assertEquals(self.cnx.nlst("potato2/potato"), [])
        self.cnx.rmd("potato2/potato")
        self.cnx.rmd("potato2")

    def test_rename_directory_into_self(self):
        '''rename a directory into itself'''
        self.cnx.mkd("potato")
        self.assertEquals(self.cnx.nlst("potato"), [])
        self.cnx.rename("potato", "/%s" % self.container)
        self.assertEquals(self.cnx.nlst("potato"), [])
        self.cnx.rename("potato", "/%s/potato" % self.container)
        self.assertEquals(self.cnx.nlst("potato"), [])
        self.cnx.rename("potato", "potato")
        self.assertEquals(self.cnx.nlst("potato"), [])
        self.cnx.rename("/%s/potato" % self.container, ".")
        self.assertEquals(self.cnx.nlst("potato"), [])
        self.cnx.rmd("potato")

    def test_rename_full_directory(self):
        '''rename a directory into a directory'''
        self.cnx.mkd("potato")
        self.create_file("potato/something.txt", "p")
        try:
            self.assertEquals(self.cnx.nlst("potato"), ["something.txt"])
            self.assertRaises(ftplib.error_perm, self.cnx.rename, "potato", "potato2")
        finally:
            self.cnx.delete("potato/something.txt")
            self.cnx.rmd("potato")

    def test_rename_container(self):
        '''rename an empty container'''
        self.cnx.mkd("/potato")
        self.assertEquals(self.cnx.nlst("/potato"), [])
        self.assertRaises(ftplib.error_perm, self.cnx.nlst, "/potato2")
        self.cnx.rename("/potato", "/potato2")
        self.assertRaises(ftplib.error_perm, self.cnx.nlst, "/potato")
        self.assertEquals(self.cnx.nlst("/potato2"), [])
        self.cnx.rmd("/potato2")

    def test_rename_full_container(self):
        '''rename a full container'''
        self.cnx.mkd("/potato")
        self.create_file("/potato/test.txt", "onion")
        self.assertEquals(self.cnx.nlst("/potato"), ["test.txt"])
        self.assertRaises(ftplib.error_perm, self.cnx.rename, "/potato", "/potato2")
        self.cnx.delete("/potato/test.txt")
        self.cnx.rmd("/potato")

    def test_unicode_file(self):
        '''Test unicode file creation'''
        # File names use a utf-8 interface
        file_name = u"Smiley\u263a.txt".encode("utf-8")
        self.create_file(file_name, "Hello Moto")
        self.assertEqual(self.cnx.nlst(), [file_name])
        self.cnx.delete(file_name)

    def test_unicode_directory(self):
        '''Test unicode directory creation'''
        # File names use a utf-8 interface
        dir_name = u"Smiley\u263aDir".encode("utf-8")
        self.cnx.mkd(dir_name)
        self.assertEqual(self.cnx.nlst(), [dir_name])
        self.cnx.rmd(dir_name)

    def test_mkdir_container_unicode(self):
        ''' mkdir/chdir/rmdir directory '''
        directory = u"/Smiley\u263aContainer".encode("utf-8")
        self.assertEqual(self.cnx.mkd(directory), directory)
        self.assertEqual(self.cnx.cwd(directory),
                         '250 "%s" is the current directory.' % (directory))
        self.assertEqual(self.cnx.rmd(directory), "250 Directory removed.")

    def test_fakedir(self):
        '''Make some fake directories and test'''

        objs = ["test1.txt", "potato/test2.txt", "potato/sausage/test3.txt",
                "potato/sausage/test4.txt",]
        for obj in objs:
            self.conn.put_object(self.container, obj, content_type="text/plain", contents="Hello Moto")

        self.assertEqual(self.cnx.nlst(), ["potato", "test1.txt"])
        self.assertEqual(self.cnx.nlst("potato"), ["sausage","test2.txt"])
        self.assertEqual(self.cnx.nlst("potato/sausage"), ["test3.txt", "test4.txt"])

        self.cnx.cwd("potato")

        self.assertEqual(self.cnx.nlst(), ["sausage","test2.txt"])
        self.assertEqual(self.cnx.nlst("sausage"), ["test3.txt", "test4.txt"])

        self.cnx.cwd("sausage")

        self.assertEqual(self.cnx.nlst(), ["test3.txt", "test4.txt"])

        self.cnx.cwd("../..")

        for obj in objs:
            self.conn.delete_object(self.container, obj)

        sleep(ListDirCache.MAX_CACHE_TIME)

        self.assertEqual(self.cnx.nlst(), [])

    def test_md5(self):
        ''' MD5 extension'''
        self.create_file("testfile.txt", "Hello Moto")
        response = self.cnx.sendcmd("MD5 /%s/testfile.txt" % self.container)
        self.cnx.delete("testfile.txt")
        self.assertEqual(response, '251 "/%s/testfile.txt" 0D933AE488FD55CC6BDEAFFFBAABF0C4' % self.container)
        self.assertRaises(ftplib.error_perm, self.cnx.sendcmd, "MD5 /%s" % self.container)
        self.assertRaises(ftplib.error_perm, self.cnx.sendcmd, "MD5 /")

    def test_retrieve_unexisting(self):
        ''' retrieve unexisting file (issue #41) '''
        store = StringIO.StringIO()
        self.assertRaises(ftplib.error_temp, self.cnx.retrbinary, "RETR nonexistent.txt", store.write)
        store.close()

    def test_resume_unexisting(self):
        ''' open unexisting file (issue #41) '''
        store = StringIO.StringIO()
        self.assertRaises(ftplib.error_perm, self.cnx.retrbinary, "RETR nonexistent.txt", store.write, rest=1000)
        store.close()

    def tearDown(self):
        # Delete eveything from the container using the API
        self.cnx.close()
        _, fails = self.conn.get_container(self.container)
        for obj in fails:
            if "name" in obj:
                self.conn.delete_object(self.container, obj["name"])
        self.conn.delete_container(self.container)
        self.assertEquals(fails, [], "The test failed to clean up after itself leaving these objects: %r" % fails)

if __name__ == '__main__':
    unittest.main()
