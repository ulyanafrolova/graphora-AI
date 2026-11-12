namespace App.Services
{
    using System.Text;

    public interface IMailer
    {
        void Send(string to);
    }

    public class Mailer : IMailer
    {
        public void Send(string to) { }
    }
}
